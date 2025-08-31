# core/services/synapse.py
# The definitive, production-ready, and canonical client for the Synapse service.
# This version combines the type-safety of Pydantic schemas with robust, defensive helpers.

from __future__ import annotations
from typing import Any, Dict, List

# Core EcodiaOS utilities for networking
from core.utils.net_api import ENDPOINTS, get_http_client

# Canonical schemas from the Synapse system source code
from systems.synapse.schemas import (
    SelectArmRequest,
    SelectArmResponse,
    LogOutcomeRequest,
    LogOutcomeResponse,
    TaskContext,
    Candidate,
    ContinueRequest,
    ContinueResponse,
    RepairRequest,
    RepairResponse,
    BudgetResponse
)

def _jsonable(x: Any) -> Any:
    """
    Robustly converts arbitrary objects (including Pydantic models) into
    JSON-safe primitives for transport.
    """
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v) for v in list(x)]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    # Pydantic v2 .model_dump() or v1 .dict()
    md = getattr(x, "model_dump", getattr(x, "dict", None))
    if callable(md):
        return _jsonable(md())
    return str(x)

class SynapseClient:
    """
    Typed adapter for the Synapse HTTP API. This client is the canonical way for
    other systems to interact with Synapse, ensuring consistent and valid payloads.
    """

    async def _request(self, method: str, path: str, json_payload: Any | None = None) -> Dict[str, Any]:
        """A consolidated, robust HTTP request helper."""
        http = await get_http_client()
        # Use the robust _jsonable helper for all outgoing data
        safe_payload = _jsonable(json_payload)
        try:
            res = await http.request(method, path, json=safe_payload, timeout=30.0)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            detail = "No response body."
            try:
                detail = res.text
            except Exception:
                pass
            print(f"[SynapseClient] CRITICAL ERROR calling {method} {path}: {e} :: {detail}")
            raise

    async def select_arm(self, task_ctx: TaskContext, candidates: List[Candidate]) -> SelectArmResponse:
        """
        Asks Synapse to select the best policy arm for a given task.
        """
        payload = SelectArmRequest(task_ctx=task_ctx, candidates=candidates)
        data = await self._request("POST", ENDPOINTS.SYNAPSE_SELECT_ARM, json_payload=payload)
        return SelectArmResponse.model_validate(data)

    async def log_outcome(
        self,
        *,
        episode_id: str,
        task_key: str,
        metrics: Dict[str, Any],
        outcome: Dict[str, Any] | None = None,
        simulator_prediction: dict[str, Any] | None = None
    ) -> LogOutcomeResponse:
        """
        Logs the final outcome of an episode to Synapse for learning.
        """
        if "chosen_arm_id" not in metrics:
            print(f"[SynapseClient] WARNING: 'chosen_arm_id' missing in metrics for episode {episode_id}. Learning may be impaired.")

        payload = LogOutcomeRequest(
            episode_id=episode_id,
            task_key=task_key,
            metrics=metrics,
            simulator_prediction=simulator_prediction or {},
        )
        
        # The /ingest/outcome endpoint is flexible; we send the Pydantic model
        # which will be serialized into the expected dictionary.
        data = await self._request("POST", ENDPOINTS.SYNAPSE_INGEST_OUTCOME, json_payload=payload)
        return LogOutcomeResponse.model_validate(data)

    async def continue_option(self, episode_id: str, last_step_outcome: dict[str, Any]) -> ContinueResponse:
        """Continues the execution of a multi-step skill (Option)."""
        req = ContinueRequest(episode_id=episode_id, last_step_outcome=last_step_outcome)
        data = await self._request("POST", ENDPOINTS.SYNAPSE_CONTINUE_OPTION, json_payload=req)
        return ContinueResponse.model_validate(data)

    async def repair_skill_step(self, episode_id: str, failed_step_index: int, error_observation: dict[str, Any]) -> RepairResponse:
        """Generates a repair action for a failed step in a skill."""
        req = RepairRequest(episode_id=episode_id, failed_step_index=failed_step_index, error_observation=error_observation)
        data = await self._request("POST", ENDPOINTS.SYNAPSE_REPAIR_SKILL, json_payload=req)
        return RepairResponse.model_validate(data)

    async def get_budget(self, task_key: str) -> BudgetResponse:
        """Returns a resource budget for a task."""
        path = ENDPOINTS.path("SYNAPSE_GET_BUDGET", task_key=task_key)
        data = await self._request("GET", path)
        return BudgetResponse.model_validate(data)

    async def registry_reload(self) -> dict[str, Any]:
        """
        Triggers a hot-reload of the Arm Registry from the database.
        """
        return await self._request("POST", ENDPOINTS.SYNAPSE_REGISTRY_RELOAD, json_payload={})

# A global singleton instance for easy importing across the system
# e.g., `from core.services.synapse import synapse`
synapse = SynapseClient()