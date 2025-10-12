# systems/synapse/core/tactics.py
# --- Hardened Tactical Manager: HoF-aware, kNN warm-start, deterministic exploration, dyn-arm on miss ---

from __future__ import annotations

import hashlib
import logging
import random
import threading
from collections.abc import Iterable
from typing import Any, Dict, List, Tuple

import numpy as np

from systems.synapse.core.registry import PolicyArm, arm_registry
from systems.synapse.rerank.episodic_knn import episodic_knn
from systems.synapse.schemas import SelectArmRequest
from systems.synapse.training.bandit_state import mark_dirty
from systems.synapse.training.neural_linear import neural_linear_manager

log = logging.getLogger(__name__)


def _stable_seed_from_ctx(task_key: str, mode: str, goal: str | None, risk: str | None) -> int:
    """Deterministic seed across identical turns; keeps exploration reproducible."""
    base = f"{mode}|{task_key}|{goal or ''}|{risk or ''}"
    return int(hashlib.sha1(base.encode("utf-8")).hexdigest()[:8], 16)


def _ensure_1d(vec: Any, d: int | None = None) -> np.ndarray:
    """Coerce to a 1-D float vector; fall back to zeros(d) if anything goes wrong."""
    try:
        arr = np.asarray(vec, dtype=float)
    except Exception:
        dim = d or getattr(neural_linear_manager, "dimensions", 64)
        arr = np.zeros((dim,), dtype=float)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    return arr


class TacticalManager:
    """
    Manages arm selection using Neural-Linear Thompson Sampling heads, with:
      - Guaranteed inclusion of Hall-of-Fame (HoF) arms
      - kNN warm-start based on episodic memory
      - Deterministic exploration drawn from remaining pool
      - Auto-registration of dynamic arms on registry miss (dev-friendly)

    Design goals:
      - Never block: if a mode has no arms or scoring fails, return a safe fallback immediately.
      - No awaits under locks.
      - Deterministic exploration per (mode, task_key, goal, risk).
    """

    _instance: TacticalManager | None = None
    _lock = threading.RLock()

    # Per-arm scratch for online updates
    _last_context_vec: dict[str, np.ndarray] = {}
    _last_scores: dict[str, dict[str, float]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ---------------- internal: candidate building ----------------

    def _build_candidate_set(
        self,
        all_arms_in_mode: list[PolicyArm],
        x_vec: np.ndarray,
        req: SelectArmRequest,
        mode: str,
        *,
        knn_k: int = 15,
        explore_cap: int = 25,
    ) -> list[PolicyArm]:
        """
        Intelligently samples a subset of arms to score.
        Strategy:
          1) Always include Hall-of-Fame arms for the mode.
          2) Add episodic kNN suggestions (if any).
          3) Add deterministic exploration sample from the rest.
        """
        total_pool = len(all_arms_in_mode)
        if total_pool == 0:
            return []

        hof_ids = arm_registry.get_hall_of_fame_arm_ids(mode)
        chosen: dict[str, PolicyArm] = {}
        added_hof = 0
        added_knn = 0
        added_explore = 0

        # 1) HoF inclusion (priority)
        for a in all_arms_in_mode:
            if a.id in hof_ids and a.id not in chosen:
                chosen[a.id] = a
                added_hof += 1

        # 2) kNN warm suggestions
        try:
            suggested_ids = episodic_knn.suggest(x_vec, k=knn_k) or []
        except Exception as e:
            log.debug(f"[Tactics-{mode}] episodic_knn.suggest failed: {e}")
            suggested_ids = []

        if suggested_ids:
            suggested_set = set(suggested_ids)
            for a in all_arms_in_mode:
                if a.id in suggested_set and a.id not in chosen:
                    chosen[a.id] = a
                    added_knn += 1

        # 3) Deterministic exploration
        remaining = [a for a in all_arms_in_mode if a.id not in chosen]
        seed = _stable_seed_from_ctx(
            req.task_ctx.task_key, mode, req.task_ctx.goal, req.task_ctx.risk_level
        )
        rnd = random.Random(seed)
        explore_n = min(explore_cap, len(remaining))
        if explore_n > 0:
            for a in rnd.sample(remaining, explore_n):
                if a.id not in chosen:
                    chosen[a.id] = a
                    added_explore += 1

        union = list(chosen.values())
        log.info(
            "[Tactics-%s] Built candidate set of size %d from pool %d (%d HoF, %d kNN, %d explore).",
            mode,
            len(union),
            total_pool,
            added_hof,
            added_knn,
            added_explore,
        )
        return union if union else all_arms_in_mode

    def _score_candidates(
        self, candidates: Iterable[PolicyArm], x_vec: np.ndarray
    ) -> dict[str, float]:
        """Score each candidate via its Neural-Linear head; skip NaN/inf safely."""
        scores: dict[str, float] = {}
        for arm in candidates:
            try:
                s = float(arm.bandit_head.score(x_vec))
                if np.isnan(s) or np.isinf(s):
                    continue
                scores[arm.id] = s
            except Exception:
                # Keep robust: one broken head must not kill scoring
                continue
        return scores

    # ---------------- public API ----------------

    async def select_arm(
        self, request: SelectArmRequest, mode: str
    ) -> tuple[PolicyArm, dict[str, float]]:
        """
        Returns (best_arm, scores_dict_for_candidates).

        - Uses request.task_ctx.mode_hint if present (soft override).
        - Encodes context via neural_linear_manager.encode; guards against failures.
        - If no arms (or scoring yields nothing), returns a safe fallback immediately.
        - On registry miss for the chosen id, tries to auto-register a dynamic arm before falling back.
        """
        final_mode = getattr(request.task_ctx, "mode_hint", None) or mode

        # Read-only registry access under lock; no awaits here.
        with self._lock:
            all_arms = arm_registry.get_arms_for_mode(final_mode)

        if not all_arms:
            log.warning("[Tactics-%s] No arms for mode. Using safe fallback.", final_mode)
            safe_arm = await arm_registry.get_safe_fallback_arm(final_mode)
            return safe_arm, {safe_arm.id: 0.0}

        # Encode context safely
        try:
            x = neural_linear_manager.encode(request.task_ctx.model_dump())
        except Exception as e:
            log.error(
                "[Tactics-%s] Failed to encode context: %s. Using zero vector.", final_mode, e
            )
            x = np.zeros((getattr(neural_linear_manager, "dimensions", 64),), dtype=float)

        x = _ensure_1d(x, d=getattr(neural_linear_manager, "dimensions", 64))

        candidates = self._build_candidate_set(all_arms, x, request, final_mode)
        if not candidates:
            log.warning(
                "[Tactics-%s] Candidate building returned empty. Using safe fallback.", final_mode
            )
            safe = await arm_registry.get_safe_fallback_arm(final_mode)
            # record scratch (without holding a lock during await)
            with self._lock:
                self._last_context_vec[safe.id] = x
                self._last_scores[safe.id] = {safe.id: 0.0}
            return safe, {safe.id: 0.0}

        scores = self._score_candidates(candidates, x)
        if not scores:
            log.warning(
                "[Tactics-%s] No candidates could be scored. Using safe fallback.", final_mode
            )
            safe = await arm_registry.get_safe_fallback_arm(final_mode)
            with self._lock:
                self._last_context_vec[safe.id] = x
                self._last_scores[safe.id] = {safe.id: 0.0}
            return safe, {safe.id: 0.0}

        # Pick best by score (stable tiebreaker on id)
        best_id = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        best_arm = arm_registry.get_policy_arm(best_id)

        # On miss, try to auto-register (dyn::) before falling back (dev-friendly)
        if not isinstance(best_arm, PolicyArm):
            try:
                best_arm = await arm_registry.get_or_register_dynamic_arm(best_id, mode=final_mode)
            except Exception:
                best_arm = None

        if not isinstance(best_arm, PolicyArm):
            log.error(
                "[Tactics-%s] Registry miss for '%s'. Using safe fallback.", final_mode, best_id
            )
            safe = await arm_registry.get_safe_fallback_arm(final_mode)
            with self._lock:
                self._last_context_vec[safe.id] = x
                self._last_scores[safe.id] = dict(scores)
            return safe, scores

        # Remember context & scores for learning
        with self._lock:
            self._last_context_vec[best_arm.id] = x
            self._last_scores[best_arm.id] = dict(scores)

        log.info(
            "[Tactics-%s] Chose arm: %s (score: %.4f)", final_mode, best_arm.id, scores[best_id]
        )
        return best_arm, scores

    def update(self, arm_id: str, reward: float) -> None:
        """
        Online update for the winning arm:
          - Neural-Linear head update
          - Episodic kNN memory update
        Clears cached context for that arm afterwards.
        """
        with self._lock:
            x = self._last_context_vec.get(arm_id)

        if x is None:
            log.warning("[Tactics] No context for arm '%s'. Cannot update.", arm_id)
            return

        arm_to_update = arm_registry.get_policy_arm(arm_id)
        if not isinstance(arm_to_update, PolicyArm):
            log.warning("[Tactics] Arm '%s' not in registry for update.", arm_id)
            # Still clear scratch so we don't leak memory
            with self._lock:
                self._last_context_vec.pop(arm_id, None)
            return

        try:
            arm_to_update.bandit_head.update(x, float(reward))
            mark_dirty(arm_id)
        except Exception as e:
            log.warning("[Tactics] bandit_head.update failed for '%s': %s", arm_id, e)

        try:
            episodic_knn.update(x, arm_id, float(reward))
        except Exception as e:
            log.warning("[Tactics] episodic_knn.update failed for '%s': %s", arm_id, e)

        with self._lock:
            self._last_context_vec.pop(arm_id, None)

        log.info(
            "[Tactics] UPDATE: Arm '%s' model and kNN updated with reward %.3f",
            arm_id,
            float(reward),
        )

    def get_last_scores_for_arm(self, arm_id: str) -> dict[str, float] | None:
        with self._lock:
            scores = self._last_scores.get(arm_id)
            return dict(scores) if scores is not None else None


tactical_manager = TacticalManager()
