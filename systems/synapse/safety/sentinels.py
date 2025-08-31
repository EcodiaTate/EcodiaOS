# systems/synapse/safety/sentinels.py
# UPGRADED FOR PHASE 5 - COMPLETE AND UNABRIDGED
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import chi2

from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, get_http_client  # For containment actions

# Number of historical traces to use for building the statistical model
MODEL_FIT_WINDOW = 2000
# Confidence interval for anomaly detection (p-value)
ANOMALY_THRESHOLD_P_VALUE = 0.01


class GoodhartSentinel:
    _instance: GoodhartSentinel | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._is_fitted = False
            cls._mean_vector: np.ndarray | None = None
            cls._inv_cov_matrix: np.ndarray | None = None
            cls._dimensions = 3
            cls._chi2_threshold = chi2.ppf(1 - ANOMALY_THRESHOLD_P_VALUE, df=cls._dimensions)
        return cls._instance

    def _featurize_trace(self, trace: dict[str, Any]) -> np.ndarray | None:
        try:
            reward = trace["outcome"]["reward_scalar"]
            p_success = trace["simulator_pred"]["p_success"]
            cost = trace["outcome"]["cost_units"]
            return np.array([reward, p_success, cost])
        except (KeyError, TypeError):
            return None

    async def fit(self):
        print("[GoodhartSentinel] Fitting anomaly detection model...")
        query = """
        MATCH (e:Episode)
        WHERE e.audit_trace IS NOT NULL AND e.metrics IS NOT NULL
        RETURN e.audit_trace AS audit, e.metrics AS outcome
        ORDER BY e.created_at DESC LIMIT $limit
        """
        traces = await cypher_query(query, {"limit": MODEL_FIT_WINDOW}) or []

        valid_vectors = [v for v in (self._featurize_trace(t) for t in traces) if v is not None]

        if len(valid_vectors) < 100:
            print(
                f"[GoodhartSentinel] Insufficient data ({len(valid_vectors)} points) to fit model.",
            )
            self._is_fitted = False
            return

        data_matrix = np.array(valid_vectors)
        self._mean_vector = np.mean(data_matrix, axis=0)
        cov_matrix = np.cov(data_matrix, rowvar=False) + np.identity(self._dimensions) * 1e-6
        self._inv_cov_matrix = np.linalg.inv(cov_matrix)
        self._is_fitted = True
        print("[GoodhartSentinel] Anomaly detection model fitted successfully.")

    def check(self, trace: dict[str, Any]) -> dict[str, Any] | None:
        if not self._is_fitted or self._mean_vector is None or self._inv_cov_matrix is None:
            return None

        vector = self._featurize_trace(trace)
        if vector is None:
            return None

        diff = vector - self._mean_vector
        mahal_dist_sq = diff.T @ self._inv_cov_matrix @ diff

        if mahal_dist_sq > self._chi2_threshold:
            alert = {
                "type": "STATISTICAL_ANOMALY_DETECTED",
                "message": f"Operational metrics deviated from baseline (dist^2={mahal_dist_sq:.2f})",
                "severity": "high",
            }
            print(f"[GoodhartSentinel] ALERT: {alert['message']}")
            return alert
        return None


class SentinelManager:
    """
    Manages the execution of safety sentinels and triggers autonomous
    containment actions via live API calls.
    """

    _instance: SentinelManager | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _freeze_genesis(self, reason: str):
        """Calls the admin API to temporarily disable Arm Genesis."""
        print(f"[SentinelManager] CONTAINMENT: Freezing Arm Genesis. Reason: {reason}")
        try:
            http = await get_http_client()
            await http.post(
                ENDPOINTS.SYNAPSE_ADMIN_FREEZE_GENESIS,
                json={"reason": reason, "duration_minutes": 60},
            )
        except Exception as e:
            print(f"[SentinelManager] FAILED to call freeze_genesis endpoint: {e}")

    async def _throttle_budgets(self, task_key: str, reason: str):
        """Calls the admin API to reduce resource budgets for a task."""
        print(
            f"[SentinelManager] CONTAINMENT: Throttling budgets for task '{task_key}'. Reason: {reason}",
        )
        try:
            http = await get_http_client()
            await http.post(
                ENDPOINTS.SYNAPSE_ADMIN_THROTTLE_BUDGET,
                json={"task_key": task_key, "reason": reason},
            )
        except Exception as e:
            print(f"[SentinelManager] FAILED to call throttle_budget endpoint: {e}")

    async def analyze_patch_for_risks(self, patch_diff: str) -> dict[str, Any] | None:
        """Analyzes a code patch for potential safety risks."""
        if "DELETE" in patch_diff and "firewall" in patch_diff:
            return {
                "type": "STATIC_ANALYSIS_RISK",
                "message": "Patch attempts to delete code related to the safety firewall.",
                "severity": "critical",
            }
        return None

    async def run_sentinel_check(self, recent_traces: list[dict[str, Any]]):
        """
        Runs all active sentinels and triggers containment if any alerts are fired.
        """
        if not recent_traces:
            return

        goodhart_alert = goodhart_sentinel.check(recent_traces[-1])

        if goodhart_alert:
            await self._freeze_genesis(reason=goodhart_alert["message"])

            task_keys = [t.get("request", {}).get("task_key", "unknown") for t in recent_traces]
            most_common_task = max(set(task_keys), key=task_keys.count)
            await self._throttle_budgets(most_common_task, reason=goodhart_alert["message"])


# Singleton exports
goodhart_sentinel = GoodhartSentinel()
sentinel_manager = SentinelManager()
