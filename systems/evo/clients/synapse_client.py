# systems/simula/client/synapse_client.py
# FIXED AND COMPLETED VERSION

from __future__ import annotations

import os
from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.synapse.schemas import (
    Candidate,
    SelectArmResponse,
    TaskContext,
)


class SynapseClient:
    """
    HTTP-only Synapse facade (pytest/CI safe; no Neo4j/driver touches):

      - select_arm(...)  → POST ENDPOINTS.SYNAPSE_SELECT_ARM
      - log_outcome(...) → POST ENDPOINTS.SYNAPSE_INGEST_OUTCOME
      - ingest_preference(...) → POST ENDPOINTS.SYNAPSE_INGEST_PREFERENCE
      - arm_inference_config(...) → best-effort model params (optional)

    Notes:
      * We do NOT import or call in-proc registries/meta_controller here.
      * All payloads use pydantic .model_dump(mode="json") for schema safety.
      * In SIMULA_TEST_MODE=1, arm_inference_config returns {} to avoid extra calls.
    """

    async def ping(self) -> dict[str, Any]:
        # If you add a health endpoint later, wire it here; for now just echo.
        return {
            "status": "ok",
            "client": "http",
            "endpoints": {
                "select": getattr(ENDPOINTS, "SYNAPSE_SELECT_ARM", None),
                "ingest": getattr(ENDPOINTS, "SYNAPSE_INGEST_OUTCOME", None),
            },
        }

    async def select_arm(
        self,
        task_ctx: TaskContext,
        candidates: list[Candidate],
    ) -> SelectArmResponse:
        """
        POST { task_ctx, candidates[] } to SYNAPSE_SELECT_ARM and
        return a validated SelectArmResponse.
        """
        http = await get_http_client()
        payload = {
            "task_ctx": task_ctx.model_dump(mode="json"),
            "candidates": [c.model_dump(mode="json") for c in (candidates or [])],
        }
        resp = await http.post(ENDPOINTS.SYNAPSE_SELECT_ARM, json=payload)
        resp.raise_for_status()
        data = resp.json()
        # Let pydantic do the validation/surface errors cleanly
        return SelectArmResponse.model_validate(data)

    async def log_outcome(
        self,
        *,
        episode_id: str,
        task_key: str,
        metrics: dict[str, Any],
        simulator_prediction: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        POST outcome to SYNAPSE_INGEST_OUTCOME.

        Required fields (per EOS bible):
          - metrics.chosen_arm_id (or top-level arm_id)
          - metrics.utility (or provide a 'success' boolean & cost; but utility preferred)
        """
        http = await get_http_client()
        payload = {
            "episode_id": episode_id,
            "task_key": task_key,
            "metrics": metrics,
            "simulator_prediction": simulator_prediction or {},
        }
        resp = await http.post(ENDPOINTS.SYNAPSE_INGEST_OUTCOME, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def ingest_preference(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        ADDED: POSTs a pairwise preference to SYNAPSE_INGEST_PREFERENCE.
        """
        http = await get_http_client()
        resp = await http.post(ENDPOINTS.SYNAPSE_INGEST_PREFERENCE, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def arm_inference_config(self, arm_id: str) -> dict[str, Any]:
        """
        OPTIONAL convenience (used by SynapseSession to hint model params).
        FIXED: The network call has been removed to prevent 404 errors,
        as the endpoint is not yet implemented. This method now always
        returns a safe, empty default.
        """
        if os.environ.get("SIMULA_TEST_MODE") == "1":
            return {}

        # The original network call is now bypassed to prevent 404s.
        # The calling code already handles this empty dict as a safe fallback.
        return {}
