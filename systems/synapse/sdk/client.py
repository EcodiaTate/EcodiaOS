# systems/synapse/sdk/client.py
# DESCRIPTION: A robust, modern client for the Synapse API, aligned with the canonical endpoints.

from __future__ import annotations

import logging
from typing import Any

from httpx import HTTPStatusError

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.synapse.schemas import (
    BudgetResponse,
    Candidate,
    ContinueRequest,
    ContinueResponse,
    LogOutcomeResponse,
    PatchProposal,
    PreferenceIngest,
    RepairRequest,
    RepairResponse,
    SelectArmRequest,
    SelectArmResponse,
    TaskContext,
)

logger = logging.getLogger(__name__)


class SynapseClient:
    """
    Typed adapter for the Synapse HTTP API. This client is the canonical way for
    other systems to interact with Synapse, ensuring consistent and valid payloads.
    """

    async def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> dict[str, Any]:
        """A consolidated, robust HTTP request helper."""
        http = await get_http_client()
        res = None  # Ensure res is defined in case of connection errors
        try:
            res = await http.request(method, path, json=json, headers=headers, timeout=10.0)
            res.raise_for_status()
            return res.json()
        except HTTPStatusError as e:
            # If the response has JSON, include it for better debugging.
            try:
                detail = e.response.json()
            except Exception:
                detail = e.response.text
            logger.error(f"SynapseClient HTTP error on {method} {path}: {e} :: {detail}")
            raise
        except Exception as e:
            logger.error(f"SynapseClient failed on {method} {path}: {e}")
            raise

    # --- Core Task Selection ---

    async def select_arm(
        self,
        task_ctx: TaskContext,
        candidates: list[Candidate] | None = None,
    ) -> SelectArmResponse:
        """Selects the best arm for a given task context and candidate set."""
        payload = SelectArmRequest(task_ctx=task_ctx, candidates=candidates or [])
        data = await self._request(
            "POST",
            ENDPOINTS.SYNAPSE_SELECT_OR_PLAN,
            json=payload.model_dump(),
        )
        return SelectArmResponse.model_validate(data)

    async def select_arm_simple(
        self,
        *,
        task_key: str,
        goal: str | None = None,
        risk_level: str | None = "medium",
        budget: str | None = "normal",
        candidate_ids: list[str] | None = None,
    ) -> SelectArmResponse:
        """Convenience wrapper for select_arm that builds models for you."""
        ctx = TaskContext(task_key=task_key, goal=goal, risk_level=risk_level, budget=budget)
        # Use the correct 'id' field for the Candidate model, and provide empty content.
        cands = [Candidate(id=aid, content={}) for aid in (candidate_ids or [])]
        return await self.select_arm(ctx, candidates=cands)

    async def continue_option(
        self,
        episode_id: str,
        last_step_outcome: dict[str, Any],
    ) -> ContinueResponse:
        """Continues the execution of a multi-step skill (Option)."""
        req = ContinueRequest(episode_id=episode_id, last_step_outcome=last_step_outcome)
        data = await self._request("POST", ENDPOINTS.SYNAPSE_CONTINUE_OPTION, json=req.model_dump())
        return ContinueResponse.model_validate(data)

    async def repair_skill_step(
        self,
        episode_id: str,
        failed_step_index: int,
        error_observation: dict[str, Any],
    ) -> RepairResponse:
        """Generates a repair action for a failed step in a skill."""
        req = RepairRequest(
            episode_id=episode_id,
            failed_step_index=failed_step_index,
            error_observation=error_observation,
        )
        data = await self._request("POST", ENDPOINTS.SYNAPSE_REPAIR_SKILL, json=req.model_dump())
        return RepairResponse.model_validate(data)

    async def get_budget(self, task_key: str) -> BudgetResponse:
        """Returns a resource budget for a task."""
        # This assumes your ENDPOINTS helper can format paths with variables.
        path = ENDPOINTS.path("SYNAPSE_GET_BUDGET", task_key=task_key)
        data = await self._request("GET", path)
        return BudgetResponse.model_validate(data)

    # --- Ingestion / Learning ---

    async def log_outcome(
        self,
        *,
        episode_id: str,
        task_key: str,
        arm_id: str | None,
        metrics: dict[str, Any],
        simulator_prediction: dict[str, Any] | None = None,
    ) -> LogOutcomeResponse:
        """Logs the final outcome of an episode, ensuring the learning loop receives correct data."""
        # Aligned payload with the LogOutcomeRequest schema and RewardArbiter.
        payload = {
            "episode_id": episode_id,
            "task_key": task_key,
            "metrics": {
                "chosen_arm_id": arm_id,
                **metrics,
            },
            "simulator_prediction": simulator_prediction or {},
        }
        data = await self._request("POST", ENDPOINTS.SYNAPSE_INGEST_OUTCOME, json=payload)
        return LogOutcomeResponse.model_validate(data)

    async def ingest_preference(
        self,
        winner: str,
        loser: str,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Ingests a pairwise preference between two arms."""
        req = PreferenceIngest(winner=winner, loser=loser, source=source)
        return await self._request(
            "POST",
            ENDPOINTS.SYNAPSE_INGEST_PREFERENCE,
            json=req.model_dump(),
        )

    # --- Governance / Registry ---

    async def submit_upgrade_proposal(self, proposal: PatchProposal) -> dict[str, Any]:
        """Submits a self-upgrade proposal to the Governor."""
        return await self._request(
            "POST",
            ENDPOINTS.SYNAPSE_GOVERNOR_SUBMIT,
            json=proposal.model_dump(),
        )

    async def reload_registry(self) -> dict[str, Any]:
        """Triggers a hot-reload of the Arm Registry from the database."""
        return await self._request("POST", ENDPOINTS.SYNAPSE_REGISTRY_RELOAD, json={})

    async def list_tools(self) -> dict[str, Any]:
        """Lists available tools from the connected Simula instance."""
        return await self._request("GET", ENDPOINTS.SYNAPSE_TOOLS)


# A singleton instance for easy importing across the system
synapse_client = SynapseClient()
