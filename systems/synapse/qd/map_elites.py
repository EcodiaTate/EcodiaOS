# systems/synapse/qd/map_elites.py
# FINAL VERSION FOR PHASE II - QD ACTIVATION (hardened)
from __future__ import annotations

import logging
import math
import threading
from typing import Any

import numpy as np

# A "niche" is a tuple of behavior descriptors, e.g., ('code', 'high', 'low_cost')
Niche = tuple[str, ...]
logger = logging.getLogger(__name__)


def _norm_str(x: Any, default: str = "unknown") -> str:
    try:
        s = str(x).strip()
        return s if s else default
    except Exception:
        return default


def _risk_tier(metrics: dict[str, Any]) -> str:
    # Accept common fields; normalize to {'low','medium','high'}
    raw = _norm_str(metrics.get("risk_level", ""), "medium").lower()
    if raw.startswith("h"):
        return "high"
    if raw.startswith("l"):
        return "low"
    return "medium"


def _cost_tier(metrics: dict[str, Any]) -> str:
    """
    Map a numeric cost signal to {low_cost, med_cost, high_cost}.
    Prefer 'cost_units'; fall back to simulator 'delta_cost' magnitude.
    """
    v: float | None = None
    try:
        if "cost_units" in metrics:
            v = float(metrics["cost_units"])
        elif "delta_cost" in metrics:
            v = abs(float(metrics["delta_cost"]))  # magnitude as proxy
    except Exception:
        v = None

    if v is None or math.isnan(v) or math.isinf(v):
        return "med_cost"
    if v < 3:
        return "low_cost"
    if v > 10:
        return "high_cost"
    return "med_cost"


def _task_family(metrics: dict[str, Any]) -> str:
    """
    Extract a stable, low-cardinality task family.
    Priority: metrics.task_family → first token of task_key → 'unknown'
    """
    fam = metrics.get("task_family")
    if fam:
        return _norm_str(fam).lower()
    tk = _norm_str(metrics.get("task_key", "unknown")).lower()
    # Use leading alpha segment before first underscore as family
    # e.g., 'simula_auto_fix' -> 'simula'
    return tk.split("_", 1)[0] if tk else "unknown"


class QDArchive:
    """
    MAP-Elites archive of diverse, high-performing PolicyArms.
    - Thread-safe updates and reads
    - Hysteresis to avoid churn on near-equal scores
    - Sampling biased toward under-sampled niches to drive exploration
    """

    _instance: QDArchive | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # self._archive[niche] = {"arm_id": str, "score": float, "count": int, "updated_at": float}
        if not hasattr(self, "_archive"):
            self._archive: dict[Niche, dict[str, Any]] = {}
            self._lock = threading.RLock()
            # independent RNG (no global state pollution)
            self._rng = np.random.default_rng()
            logger.info("[QDArchive] Quality-Diversity archive initialized.")

    # ---------------------------
    # Descriptor
    # ---------------------------
    def get_descriptor(self, arm_id: str, metrics: dict[str, Any]) -> Niche:
        """
        Compute a behavioral descriptor (niche) for a policy based on its
        observed performance and context.
        """
        risk = _risk_tier(metrics)
        cost = _cost_tier(metrics)
        family = _task_family(metrics)
        return (family, risk, cost)

    # ---------------------------
    # Insert / Update
    # ---------------------------
    def insert(self, arm_id: str, score: float, metrics: dict[str, Any]):
        """
        Insert/update an arm in the archive based on its niche and score.
        Replaces the champion only if new score is higher by a small epsilon.
        """
        niche = self.get_descriptor(arm_id, metrics)
        eps = 1e-9  # hysteresis to prevent churn on ties

        with self._lock:
            slot = self._archive.get(niche)
            if slot is None:
                self._archive[niche] = {
                    "arm_id": arm_id,
                    "score": float(score),
                    "count": 1,
                    "updated_at": self._rng.random(),  # inexpensive monotonic-ish marker
                }
                logger.info(
                    "[QDArchive] New niche discovered %s -> champion=%s score=%.4f",
                    niche,
                    arm_id,
                    float(score),
                )
                return

            # Update visit count regardless (used for exploration bias)
            slot["count"] = int(slot.get("count", 0)) + 1

            curr = float(slot.get("score", float("-inf")))
            if float(score) > (curr + eps):
                prev = slot.get("arm_id")
                slot["arm_id"] = arm_id
                slot["score"] = float(score)
                slot["updated_at"] = self._rng.random()
                logger.info(
                    "[QDArchive] Champion updated niche=%s prev=%s → new=%s score=%.4f",
                    niche,
                    prev,
                    arm_id,
                    float(score),
                )

    # ---------------------------
    # Sampling
    # ---------------------------
    def sample_niche(self) -> Niche | None:
        """
        Sample a niche with bias toward under-sampled entries to promote coverage.
        Weight formula: w = 1 / sqrt(count + 1)
        """
        with self._lock:
            if not self._archive:
                return None
            niches: list[Niche] = list(self._archive.keys())
            counts = np.array([int(self._archive[n].get("count", 0)) for n in niches], dtype=float)
            weights = 1.0 / np.sqrt(counts + 1.0)
            weights_sum = float(weights.sum())
            if weights_sum <= 0.0 or not np.isfinite(weights_sum):
                # fallback to uniform
                idx = int(self._rng.integers(low=0, high=len(niches)))
                return niches[idx]
            probs = weights / weights_sum
            idx = int(self._rng.choice(len(niches), p=probs))
            return niches[idx]

    # ---------------------------
    # Queries
    # ---------------------------
    def get_champion_from_niche(self, niche: Niche) -> str | None:
        """Return the champion arm_id for a given niche (or None)."""
        with self._lock:
            slot = self._archive.get(niche)
            return None if slot is None else _norm_str(slot.get("arm_id"), "") or None


# Singleton export
qd_archive = QDArchive()
