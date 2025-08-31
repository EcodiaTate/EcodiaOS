# systems/equor/core/self/predictor.py
from __future__ import annotations

from typing import Any

import numpy as np

from core.services.synapse import synapse
from core.utils.neo.cypher_query import cypher_query


class SelfModel:
    """
    Singleton that predicts Equor's next subjective-state vector.
    It first attempts to call Synapse's model-serving API; if unavailable,
    it estimates the next state from historical QualiaState transitions in Neo4j.
    """

    _instance: SelfModel | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.synapse = synapse  # <-- remove the () here
        return cls._instance

    async def _try_synapse_predict(
        self,
        current_qualia_coordinates: list[float],
        task_context: dict[str, Any],
    ) -> list[float] | None:
        """
        Attempt to use Synapse's generic model prediction endpoint.
        Expects a payload containing 'predicted_state_vector'.
        """
        req = {
            "model_id": "equor_self_model_transformer_v1",
            "inputs": {
                "current_state_vector": current_qualia_coordinates,
                "task_context_features": task_context,
            },
        }
        try:
            # If SynapseClient exposes a `predict` coroutine, use it.
            predict_fn = getattr(self.synapse, "predict", None)
            if predict_fn is None:
                return None
            resp = await predict_fn(req)
            # Support multiple common shapes
            if isinstance(resp, dict):
                vec = resp.get("predicted_state_vector") or resp.get("vector")
                if isinstance(vec, list) and all(isinstance(x, int | float) for x in vec):
                    return [float(x) for x in vec]
            # Pydantic-style access
            if hasattr(resp, "predicted_state_vector"):
                vec = getattr(resp, "predicted_state_vector")
                if isinstance(vec, list):
                    return [float(x) for x in vec]
        except Exception as e:
            print(f"[SelfModel] Synapse prediction unavailable: {e!r}")
        return None

    async def _estimate_from_history(
        self,
        current_qualia_coordinates: list[float],
        task_context: dict[str, Any],
        limit: int = 1000,
    ) -> list[float] | None:
        """
        Build a simple, data-driven estimator from recent (state -> next_state) pairs.
        Uses task-specific transitions when possible; otherwise falls back to global pairs.
        Returns current + mean_delta across matched pairs.
        """
        task_key = str(task_context.get("task_key") or task_context.get("task") or "")
        params = {"limit": limit, "task_key": task_key}

        def _pairs_where(where_clause: str) -> str:
            return f"""
            MATCH (e1:Episode)-[:EXPERIENCED]->(qs1:QualiaState)
            MATCH (e2:Episode)-[:EXPERIENCED]->(qs2:QualiaState)
            WHERE {where_clause} AND e2.created_at > e1.created_at
            WITH e1, qs1, e2, qs2
            ORDER BY e2.created_at ASC
            WITH e1, qs1, head(collect(qs2)) AS next_qs
            RETURN qs1.manifold_coordinates AS s1,
                   next_qs.manifold_coordinates AS s2
            ORDER BY e1.created_at DESC
            LIMIT $limit
            """

        # 1) Try task-specific transitions first (if we have a task key)
        rows: list = []
        if task_key:
            rows = (
                await cypher_query(
                    _pairs_where("e1.task_key = $task_key AND e2.task_key = $task_key"),
                    params,
                )
                or []
            )

        # 2) Fallback to global transitions if not enough data
        if len(rows) < 20:
            rows = await cypher_query(_pairs_where("true"), {"limit": limit}) or []

        if not rows:
            return None

        cur = np.asarray(current_qualia_coordinates, dtype=float).reshape(-1)
        d_list = []
        for r in rows:
            s1 = r.get("s1")
            s2 = r.get("s2")
            if not isinstance(s1, list) or not isinstance(s2, list):
                continue
            v1 = np.asarray(s1, dtype=float).reshape(-1)
            v2 = np.asarray(s2, dtype=float).reshape(-1)
            if v1.shape != v2.shape or v1.shape != cur.shape:
                continue
            d_list.append(v2 - v1)

        if not d_list:
            return None

        # Robust mean delta with outlier trimming
        D = np.vstack(d_list)  # [N, d]
        # Trim 10% tails per-dimension
        lower = np.percentile(D, 10, axis=0)
        upper = np.percentile(D, 90, axis=0)
        mask = np.all((D >= lower) & (D <= upper), axis=1)
        D_trim = D[mask] if np.any(mask) else D
        mean_delta = D_trim.mean(axis=0)

        pred = cur + mean_delta
        return pred.astype(float).tolist()

    async def predict_next_state(
        self,
        current_qualia_coordinates: list[float],
        task_context: dict[str, Any],
    ) -> list[float]:
        """
        Predict the next QualiaManifold coordinates:
          1) Try Synapse-hosted model.
          2) Fallback: estimate from historical transitions.
          3) Last resort: identity prediction.
        """
        print("[SelfModel] Predicting next subjective state...")

        # 1) Synapse model (if available)
        syn = await self._try_synapse_predict(current_qualia_coordinates, task_context)
        if syn is not None and len(syn) == len(current_qualia_coordinates):
            print("[SelfModel] Using Synapse-served prediction.")
            return syn

        # 2) Historical estimator
        hist = await self._estimate_from_history(current_qualia_coordinates, task_context)
        if hist is not None and len(hist) == len(current_qualia_coordinates):
            print("[SelfModel] Using graph-derived historical estimator.")
            return hist

        # 3) Identity fallback
        print("[SelfModel] Falling back to identity prediction.")
        return [float(x) for x in current_qualia_coordinates]


# Singleton export
self_model = SelfModel()
