# systems/synapse/core/tactics.py
# FULLY CORRECTED AND MODERNIZED (cold-start safe, deterministic, replayable)
from __future__ import annotations

import hashlib
import random
import threading
from collections.abc import Iterable
from typing import Any

import numpy as np

from systems.synapse.core.registry import PolicyArm, arm_registry
from systems.synapse.rerank.episodic_knn import episodic_knn
from systems.synapse.schemas import SelectArmRequest
from systems.synapse.training.bandit_state import mark_dirty
from systems.synapse.training.neural_linear import neural_linear_manager


def _stable_seed_from_ctx(
    task_key: str,
    mode: str,
    goal: str | None,
    risk: str | None,
) -> int:
    base = f"{mode}|{task_key}|{goal or ''}|{risk or ''}"
    return int(hashlib.sha1(base.encode("utf-8")).hexdigest()[:8], 16)


def _ensure_1d(vec: Any, d: int | None = None) -> np.ndarray:
    try:
        arr = np.asarray(vec, dtype=float)
    except Exception:
        arr = np.zeros((d or getattr(neural_linear_manager, "dimensions", 64),), dtype=float)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    return arr


class TacticalManager:
    """
    Manages arm selection per mode using Neural-Linear TS heads on each PolicyArm.
    Cold-start tolerant, deterministic (seeded by task context), kNN-warmstarted.
    """

    _instance: TacticalManager | None = None
    _lock = threading.RLock()

    # Caches for audit/update
    _last_context_vec: dict[str, np.ndarray] = {}
    _last_scores: dict[str, dict[str, float]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _candidate_ids_from_request(self, req: SelectArmRequest) -> list[str]:
        try:
            return [c.arm_id for c in (req.candidates or []) if getattr(c, "arm_id", None)]
        except Exception:
            return []

    def _build_candidate_set(
        self,
        all_arms_in_mode: list[PolicyArm],
        x_vec: np.ndarray,
        req: SelectArmRequest,
        mode: str,
    ) -> list[PolicyArm]:
        # 1) honor explicit candidates if provided and present in registry
        explicit_ids = set(self._candidate_ids_from_request(req))
        if explicit_ids:
            cand = [a for a in all_arms_in_mode if a.id in explicit_ids]
            if cand:
                return cand

        # 2) warm start from episodic kNN (best-effort)
        try:
            suggested_ids = episodic_knn.suggest(x_vec) or []
        except Exception:
            suggested_ids = []
        warm = {a.id: a for a in all_arms_in_mode if a.id in suggested_ids}

        # 3) deterministic exploration sample (replayable)
        rnd = random.Random(
            _stable_seed_from_ctx(
                req.task_ctx.task_key,
                mode,
                req.task_ctx.goal,
                req.task_ctx.risk_level,
            ),
        )
        pool = [a for a in all_arms_in_mode if a.id not in warm]
        sample_n = min(5, len(pool))
        explore = rnd.sample(pool, sample_n) if sample_n > 0 else []

        # 4) union; if still empty, use all
        union = list(warm.values()) + explore
        return union if union else list(all_arms_in_mode)

    def _score_candidates(
        self,
        candidates: Iterable[PolicyArm],
        x_vec: np.ndarray,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for arm in candidates:
            try:
                s = float(arm.bandit_head.score(x_vec))
                if np.isnan(s) or np.isinf(s):
                    continue
                scores[arm.id] = s
            except Exception:
                # skip broken heads; do not fail selection
                continue
        return scores

    def select_arm(
        self,
        request: SelectArmRequest,
        mode: str,
    ) -> tuple[PolicyArm, dict[str, float]]:
        """
        Returns (best_arm, scores). Never raises on cold start.
        """
        with self._lock:
            arms = arm_registry.get_arms_for_mode(mode)
            if not arms:
                # escalate to caller to try fallback mode; if they don't, fail safely there
                raise ValueError(f"No arms found for mode '{mode}' in ArmRegistry.")

            # Encode task context (best-effort)
            try:
                x = neural_linear_manager.encode(request.task_ctx.model_dump())
            except Exception:
                x = np.zeros((getattr(neural_linear_manager, "dimensions", 64),), dtype=float)
            x = _ensure_1d(x, d=getattr(neural_linear_manager, "dimensions", 64))

            # Candidates
            candidates = self._build_candidate_set(arms, x, request, mode)

            # Scores
            scores = self._score_candidates(candidates, x)

            # If nothing scored (extreme cold-start), pick registry safe fallback for this mode
            if not scores:
                safe = arm_registry.get_safe_fallback_arm(mode)
                # cache minimal context & zero score to keep downstream consistent
                self._last_context_vec[safe.id] = x
                self._last_scores[safe.id] = {safe.id: 0.0}
                print(f"[Tactics-{mode}] Cold-start fallback: {safe.id} (no scoreable candidates).")
                return safe, {safe.id: 0.0}

            # Deterministic tie-break: highest score, then lexicographic id
            best_id = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            best_arm = arm_registry.get_arm(best_id)
            if best_arm is None:
                # extremely unlikely; fall back to safe arm
                safe = arm_registry.get_safe_fallback_arm(mode)
                self._last_context_vec[safe.id] = x
                self._last_scores[safe.id] = {safe.id: scores.get(safe.id, 0.0)}
                print(
                    f"[Tactics-{mode}] Registry miss for '{best_id}', using safe fallback '{safe.id}'.",
                )
                return safe, {safe.id: scores.get(safe.id, 0.0)}

            # Cache for update/audit
            self._last_context_vec[best_arm.id] = x
            self._last_scores[best_arm.id] = dict(scores)

            print(
                f"[Tactics-{mode}] Chose arm: {best_arm.id} (score: {scores[best_id]:.4f}) from {len(scores)} candidates.",
            )
            return best_arm, scores

    def update(self, arm_id: str, reward: float) -> None:
        """
        Updates the specific bandit head of the chosen arm and the episodic kNN index.
        Best-effort; never raises.
        """
        with self._lock:
            x = self._last_context_vec.get(arm_id)
            if x is None:
                print(f"[Tactics] WARNING: No context found for arm '{arm_id}'. Cannot update.")
                return

            arm_to_update = arm_registry.get_arm(arm_id)
            if not arm_to_update:
                print(f"[Tactics] WARNING: Arm '{arm_id}' not found in registry for update.")
                return

            try:
                arm_to_update.bandit_head.update(x, float(reward))
                mark_dirty(arm_id)
            except Exception as e:
                print(f"[Tactics] WARNING: bandit_head.update failed for '{arm_id}': {e}")

            try:
                episodic_knn.update(x, arm_id, float(reward))
            except Exception as e:
                print(f"[Tactics] WARNING: episodic_knn.update failed for '{arm_id}': {e}")

            # Pop after use to prevent re-updating
            self._last_context_vec.pop(arm_id, None)
            print(
                f"[Tactics] UPDATE: Arm '{arm_id}' model and kNN index updated with reward {float(reward):.3f}",
            )

    def get_last_scores_for_arm(self, arm_id: str) -> dict[str, float] | None:
        """Expose last scores used when selecting this arm (for auditing)."""
        with self._lock:
            return self._last_scores.get(arm_id)


# Singleton export
tactical_manager = TacticalManager()
