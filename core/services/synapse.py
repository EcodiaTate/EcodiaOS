# core/services/synapse.py
# --- DEFINITIVE, CORRECTED & COMPLETE CLIENT ---

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterable
from typing import Any, Dict, List, Optional

import httpx

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.synapse.policy.policy_dsl import PolicyGraph
from systems.synapse.schemas import (
    BudgetResponse,
    Candidate,
    ContinueRequest,
    ContinueResponse,
    LogOutcomeRequest,
    LogOutcomeResponse,
    PatchProposal,
    RepairRequest,
    RepairResponse,
    SelectArmRequest,
    SelectArmResponse,
    SimulateResponse,
    SMTCheckRequest,
    SMTCheckResponse,
    TaskContext,
)

logger = logging.getLogger(__name__)


def _jsonable(x: Any) -> Any:
    """Recursively converts an object to be JSON-serializable for HTTP transport."""
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v) for v in list(x)]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    md = getattr(x, "model_dump", getattr(x, "dict", None))
    if callable(md):
        try:
            return _jsonable(md())
        except Exception:
            pass
    return str(x)


class SynapseClient:
    """Typed adapter for the Synapse HTTP API. This is the canonical client."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Consolidated, robust HTTP request helper.

        - Uses the shared AsyncClient from get_http_client() (base URL, session reuse)
        - Applies a single total-timeout (env SYNAPSE_HTTP_TIMEOUT, default 120s)
        - Retries on:
            * 503 with warmup hint in body (bootstrap not ready)
            * Read/Connect timeouts
        - Logs rich diagnostics including server body when available
        """
        http = await get_http_client()
        safe_payload = _jsonable(json_payload)

        # Environment-configurable behavior
        total_timeout = float(os.getenv("SYNAPSE_HTTP_TIMEOUT", "120.0"))
        retries = int(os.getenv("SYNAPSE_HTTP_RETRIES", "3"))
        backoff_base = float(os.getenv("SYNAPSE_HTTP_BACKOFF_BASE", "0.25"))

        timeout_cfg = httpx.Timeout(total_timeout)

        last_exc: Exception | None = None
        for attempt in range(retries):
            res: httpx.Response | None = None
            try:
                res = await http.request(
                    method,
                    path,  # NOTE: get_http_client() should include base_url
                    json=safe_payload,
                    headers=headers,
                    timeout=timeout_cfg,
                )

                # Retry on ANY 503 (hot reloads / bootstrap)
                if res.status_code == 503 and attempt < retries - 1:
                    await asyncio.sleep(backoff_base * (attempt + 1))
                    continue

                res.raise_for_status()
                if not res.content:
                    raise httpx.ReadTimeout("No response body.")
                return res.json()

            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
                if attempt < retries - 1:
                    await asyncio.sleep(backoff_base * (attempt + 1))
                    continue
                # fall through to log + raise

            except httpx.HTTPStatusError as e:
                # HTTP status outside 2xx after raise_for_status(); include body if any
                body_text = ""
                try:
                    if e.response is not None:
                        body_text = e.response.text
                except Exception:
                    pass
                logger.error(
                    "[SynapseClient] HTTP %s %s -> %s :: %s",
                    method,
                    path,
                    getattr(e.response, "status_code", "?"),
                    body_text,
                    exc_info=True,
                )
                raise

            except Exception as e:
                last_exc = e
                logger.error(
                    "[SynapseClient] CRITICAL ERROR %s %s: %s",
                    method,
                    path,
                    e,
                    exc_info=True,
                )
                raise

        logger.error(
            "[SynapseClient] Exhausted retries for %s %s :: %s",
            method,
            path,
            last_exc or "unknown error",
            exc_info=True,
        )
        raise last_exc or httpx.ReadTimeout("Request failed with no additional context.")

    # ===== Decision Surfaces =====

    async def select_or_plan(
        self,
        task_ctx: TaskContext,
        candidates: list[Candidate],
        *,
        headers: dict[str, str] | None = None,
        exclude_prefixes: Iterable[str] = ("dyn::", "reflex::"),
        max_retries: int = int(os.getenv("SIMULA_MAX_STATIC_RETRIES", "3")),
        backoff_s: float = float(os.getenv("SIMULA_STATIC_RETRY_BACKOFF_S", "0.25")),
    ) -> SelectArmResponse:
        """
        Preferred entrypoint for all decisions.
        GUARANTEES: returns a **static** policy arm (filters out dynamic arms locally).

        - Sends a best-effort hint to the server via task_ctx.metadata['arm_id_exclude_prefixes'].
        - Retries client-side if the server still returns an excluded arm id.
        """
        # Non-destructive metadata augmentation
        md = dict(task_ctx.metadata or {})
        md.setdefault("arm_id_exclude_prefixes", list(exclude_prefixes))
        safe_ctx = TaskContext(task_key=task_ctx.task_key, goal=task_ctx.goal, metadata=md)

        path = getattr(ENDPOINTS, "SYNAPSE_SELECT_OR_PLAN", "/synapse/select_or_plan")
        last_err: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                payload = SelectArmRequest(task_ctx=safe_ctx, candidates=candidates)
                data = await self._request("POST", path, json_payload=payload, headers=headers)
                sel = SelectArmResponse.model_validate(data)

                arm_id = (sel.champion_arm.arm_id or "").strip()
                if any(arm_id.startswith(pref) for pref in exclude_prefixes):
                    logger.warning(
                        "[SynapseClient] Rejected dynamic arm '%s' (attempt %d/%d)",
                        arm_id,
                        attempt,
                        max_retries,
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(backoff_s)
                        continue
                    # Exhausted
                    raise RuntimeError(
                        f"Synapse returned only dynamic arms after {max_retries} attempt(s). "
                        f"Last arm: {arm_id or '—'}",
                    )

                # OK: static arm
                return sel

            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    await asyncio.sleep(backoff_s)
                    continue
                logger.error(
                    "[SynapseClient] select_or_plan failed after %d attempts: %r",
                    attempt,
                    e,
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Synapse did not return a static strategy after {max_retries} attempt(s). "
                    f"Last error: {repr(last_err) if last_err else '—'}",
                )

    # ===== Semantic Validation / Modeling =====

    async def simulate(self, policy_graph: PolicyGraph, task_ctx: TaskContext) -> SimulateResponse:
        """Calls the World Model to predict the outcome of a policy graph."""
        payload = {"policy_graph": policy_graph.model_dump(), "task_ctx": task_ctx.model_dump()}
        path = getattr(ENDPOINTS, "SYNAPSE_SIMULATE", "/synapse/models/simulate")
        data = await self._request("POST", path, json_payload=payload)
        return SimulateResponse.model_validate(data)

    async def smt_check(self, policy_graph: PolicyGraph) -> SMTCheckResponse:
        """Calls the SMT Guard to check a policy graph for formal constraint violations."""
        payload = SMTCheckRequest(policy_graph=policy_graph)
        path = getattr(ENDPOINTS, "SYNAPSE_SMT_CHECK", "/synapse/firewall/smt_check")
        data = await self._request("POST", path, json_payload=payload)
        return SMTCheckResponse.model_validate(data)

    # ===== Learning & Control =====

    async def log_outcome(
        self,
        *,
        episode_id: str,
        task_key: str,
        metrics: dict[str, Any],
        simulator_prediction: dict[str, Any] | None = None,
    ) -> LogOutcomeResponse:
        """
        Logs the final outcome of an episode to close the learning loop.
        Notes:
          - Ensure 'chosen_arm_id' is present to help downstream analytics.
        """
        if "chosen_arm_id" not in metrics and "arm_id" not in metrics:
            logger.warning(
                "[SynapseClient] 'chosen_arm_id' missing in metrics for episode %s.",
                episode_id,
            )

        payload = LogOutcomeRequest(
            episode_id=episode_id,
            task_key=task_key,
            metrics=metrics,
            simulator_prediction=simulator_prediction,
        )
        path = getattr(ENDPOINTS, "SYNAPSE_INGEST_OUTCOME", "/synapse/ingest/outcome")
        data = await self._request("POST", path, json_payload=payload)
        return LogOutcomeResponse.model_validate(data)

    async def continue_option(
        self,
        episode_id: str,
        last_step_outcome: dict[str, Any],
    ) -> ContinueResponse:
        """Continues execution of a multi-step hierarchical skill."""
        req = ContinueRequest(episode_id=episode_id, last_step_outcome=last_step_outcome)
        path = getattr(ENDPOINTS, "SYNAPSE_CONTINUE_OPTION", "/synapse/tasks/continue_option")
        data = await self._request("POST", path, json_payload=req)
        return ContinueResponse.model_validate(data)

    async def repair_skill_step(
        self,
        episode_id: str,
        failed_step_index: int,
        error_observation: dict[str, Any],
    ) -> RepairResponse:
        """Requests a one-shot repair action for a failed skill step."""
        req = RepairRequest(
            episode_id=episode_id,
            failed_step_index=failed_step_index,
            error_observation=error_observation,
        )
        path = getattr(ENDPOINTS, "SYNAPSE_REPAIR_SKILL", "/synapse/tasks/repair_skill_step")
        data = await self._request("POST", path, json_payload=req)
        return RepairResponse.model_validate(data)

    # ===== Governance & Registry =====

    async def submit_upgrade_proposal(self, proposal: PatchProposal) -> dict[str, Any]:
        """Submits a self-upgrade proposal to the Governor for formal verification."""
        path = getattr(ENDPOINTS, "SYNAPSE_GOVERNOR_SUBMIT", "/synapse/governor/submit_proposal")
        return await self._request("POST", path, json_payload=proposal)

    async def registry_reload(self) -> dict[str, Any]:
        """Triggers a hot-reload of the in-memory Arm Registry from the database."""
        path = getattr(ENDPOINTS, "SYNAPSE_REGISTRY_RELOAD", "/synapse/registry/reload")
        return await self._request("POST", path, json_payload={})


# Global singleton for easy access
synapse = SynapseClient()
