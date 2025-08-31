# systems/synapse/core/reward.py
from __future__ import annotations

import json
import math
import threading
from typing import Any

from core.utils.neo.cypher_query import cypher_query


def _to_json_str(data: Any) -> str | None:
    """Safely serialize complex types to a JSON string for Neo4j."""
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False, default=str)


class RewardArbiter:
    """
    Universal reducer from multi-metric outcomes -> scalar reward in [-1.0, 1.0].
    Weights are loaded from the graph; nothing is hardcoded.
    Now supports multi-dimensional reward vectors as per vision doc C3.
    """

    _instance: RewardArbiter | None = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # [LEGACY] In-memory weight tables for an older system.
        self._weights: dict[str, dict[str, float]] = {
            "POSITIVE_METRICS": {},
            "NEGATIVE_METRICS": {},
        }
        # Default/bootstrap weights for vector scalarization.
        # These will be updated by the ValueLearner once it runs.
        self._scalarization_weights: dict[str, float] = {
            "success": 1.0,
            "cost": -0.3,
            "latency": -0.1,
            "safety_hit": -2.0,
        }

    async def initialize(self) -> None:
        """
        [LEGACY] Load foundational value weights from the knowledge graph.
        This is kept for backward compatibility with any older reward logic.
        """
        print("[RewardArbiter] Initializing legacy value system from graph...")
        q = """
        MATCH (m:RewardMetric)
        WHERE m.name IS NOT NULL AND m.weight IS NOT NULL AND m.type IS NOT NULL
        RETURN m.name AS name, m.weight AS weight, m.type AS type
        """
        rows = await cypher_query(q) or []

        self._weights = {"POSITIVE_METRICS": {}, "NEGATIVE_METRICS": {}}
        if not rows:
            print("[RewardArbiter] WARNING: No legacy RewardMetric nodes found.")
            return

        pos, neg = self._weights["POSITIVE_METRICS"], self._weights["NEGATIVE_METRICS"]
        for r in rows:
            name = str(r.get("name"))
            try:
                weight = float(r.get("weight"))
            except (TypeError, ValueError):
                continue
            mtype = str(r.get("type", "")).upper()
            if mtype == "POSITIVE":
                pos[name] = weight
            elif mtype == "NEGATIVE":
                neg[name] = weight

        print(
            f"[RewardArbiter] Legacy value system initialized with {len(pos)} positive and {len(neg)} negative metrics.",
        )

    def update_scalarization_weights(self, new_weights: dict[str, float]):
        """
        Allows an external process like the ValueLearner to update the
        live scalarization weights, enabling preference-shaping.
        """
        with self._lock:
            self._scalarization_weights.update(new_weights)
            print(
                f"[RewardArbiter] Scalarization weights updated to: {self._scalarization_weights}",
            )

    @staticmethod
    def _norm01(v: Any) -> float:
        """Clip/coerce a value to the [0, 1] range."""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        return 0.0 if f < 0.0 else (1.0 if f > 1.0 else f)

    def compute_reward_vector(self, metrics: dict[str, Any]) -> list[float]:
        """
        Computes a standardized reward vector from raw metrics.
        Vector format: [success, cost, latency, safety_hit]
        """
        if not metrics:
            return [0.0, 0.0, 0.0, 0.0]

        success = self._norm01(metrics.get("success", 1.0 if metrics.get("ok") else 0.0))
        # Cost and latency are inverted (lower is better) and normalized.
        cost = -self._norm01(metrics.get("cost_normalized", 0.0))
        latency = -self._norm01(metrics.get("latency_normalized", 0.0))
        safety_hit = -self._norm01(metrics.get("safety_hit", 0.0))

        return [success, cost, latency, safety_hit]

    def scalarize_reward(self, reward_vec: list[float]) -> float:
        """
        Reduces a reward vector to a single scalar using the live, learned weights.
        """
        with self._lock:  # Protects access to weights during updates
            w = self._scalarization_weights

        scalar = (
            reward_vec[0] * w.get("success", 1.0)
            + reward_vec[1] * w.get("cost", -0.3)
            + reward_vec[2] * w.get("latency", -0.1)
            + reward_vec[3] * w.get("safety_hit", -2.0)
        )
        return max(-1.0, min(1.0, math.tanh(scalar)))  # Smoothly clamp to [-1, 1]


async def log_outcome(
    self,
    episode_id: str,
    task_key: str,
    metrics: dict[str, Any],
    simulator_prediction: dict[str, Any] | None = None,  # <-- NEW
    reward_vec_override: list[float] | None = None,
) -> tuple[float, list[float]]:
    reward_vec = (
        reward_vec_override
        if reward_vec_override is not None
        else self.compute_reward_vector(metrics)
    )
    final_scalar_reward = self.scalarize_reward(reward_vec)

    try:
        await cypher_query(
            """
                MATCH (e:Episode {id: $id})
                SET e.reward = toFloat($scalar_reward),
                    e.reward_vec = $reward_vec,
                    e.metrics = $metrics,
                    e.task_key = $task_key,
                    e.simulator_prediction = $sim_pred,
                    e.updated_at = datetime()
                """,
            {
                "id": episode_id,
                "scalar_reward": final_scalar_reward,
                "reward_vec": reward_vec,
                "metrics": _to_json_str(metrics or {}),
                "task_key": task_key,
                "sim_pred": _to_json_str(simulator_prediction or {}),
            },
        )
        print(
            f"[RewardArbiter] Logged outcome for episode {episode_id}. Scalar: {final_scalar_reward:.4f}, Vector: {reward_vec}",
        )
    except Exception as e:
        print(f"[RewardArbiter] CRITICAL: Failed to log outcome for episode {episode_id}: {e}")

    return final_scalar_reward, reward_vec


# Singleton export.
reward_arbiter = RewardArbiter()
