# systems/synapse/economics/roi.py
from __future__ import annotations

from typing import Any


class ROIManager:
    """
    Tracks the Return on Investment (ROI) for each policy arm.
    """

    _instance: ROIManager | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # arm_id -> {"total_reward": float, "total_cost": float, "count": int}
        self._ledger: dict[str, dict[str, float]] = {}
        print("[ROIManager] Economics layer initialized.")

    def update_roi(self, arm_id: str, scalar_reward: float, metrics: dict[str, Any]):
        """
        Updates the ROI ledger for an arm after an episode completes.
        """
        cost = metrics.get("cost_units", 1.0)  # Assume a base cost if not provided

        if arm_id not in self._ledger:
            self._ledger[arm_id] = {"total_reward": 0.0, "total_cost": 0.0, "count": 0}

        entry = self._ledger[arm_id]
        entry["total_reward"] += scalar_reward
        entry["total_cost"] += cost
        entry["count"] += 1

    def get_underperforming_arms(self, percentile_threshold: int = 10) -> list[str]:
        """
        Scans the ledger and returns a list of arms in the bottom Nth percentile for ROI.
        These are candidates for pruning by the genesis module.
        """
        if not self._ledger:
            return []

        rois = {}
        for arm_id, data in self._ledger.items():
            if data["total_cost"] > 0 and data["count"] > 10:  # Only consider arms with enough data
                rois[arm_id] = data["total_reward"] / data["total_cost"]

        if not rois:
            return []

        # Find the ROI value at the given percentile
        roi_values = sorted(rois.values())
        if not roi_values:
            return []

        threshold_index = len(roi_values) * percentile_threshold // 100
        roi_threshold = roi_values[threshold_index]

        underperformers = [arm_id for arm_id, roi in rois.items() if roi <= roi_threshold]
        print(
            f"[ROIManager] Found {len(underperformers)} underperforming arms below {percentile_threshold}th percentile (ROI < {roi_threshold:.3f})",
        )
        return underperformers


# Singleton export
roi_manager = ROIManager()
