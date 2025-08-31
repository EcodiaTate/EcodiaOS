# core/prompting/orchestrator.py
# --- PROJECT SENTINEL UPGRADE (FINAL CONSOLIDATED) ---
from __future__ import annotations

import uuid
import httpx
from dataclasses import dataclass
from typing import Any

# Core EcodiaOS imports
from core.prompting.registry import get_registry
from core.prompting.runtime import (
    LLMResponse,
    RenderedPrompt,
    parse_and_validate,
    render_prompt,
)
from core.prompting.spec import PromptSpec


# --- Types for API compatibility ---
@dataclass
class PolicyHint:
    """A hint to the orchestrator about which prompt to build and what context to use."""

    scope: str
    summary: str = ""
    task_key: str | None = None
    context: dict[str, Any] | None = None  # Expected to be a state dictionary


@dataclass
class OrchestratorResponse:
    """The structured output from building a prompt."""

    messages: list[dict[str, str]]
    provider_overrides: dict[str, Any]
    provenance: dict[str, Any]


# --- Core helper with Smart Fallback ---
def _resolve_spec(scope: str) -> PromptSpec:
    """
    Finds the correct PromptSpec from the registry. If not found, raises a
    clear error, as missing specs should be treated as configuration errors.
    """
    registry = get_registry()
    spec = registry.get_by_scope(scope)

    if spec:
        return spec

    raise ValueError(
        f"CRITICAL: No PromptSpec found for scope '{scope}'. Please ensure a spec file exists."
    )


# --- Public API ---


async def build_prompt(hint: PolicyHint) -> OrchestratorResponse:
    """
    Renders prompt messages and provider settings based on a loaded PromptSpec
    and a rich context dictionary. This is the primary entry point for preparing an LLM call.
    """
    spec = _resolve_spec(hint.scope)

    rendered_prompt: RenderedPrompt = await render_prompt(
        spec=spec,
        context_dict=hint.context or {},
        task_summary=hint.summary or f"Scope: {hint.scope}",
    )

    overrides = rendered_prompt.provider_overrides

    return OrchestratorResponse(
        messages=rendered_prompt.messages,
        provider_overrides={
            "max_tokens": overrides.max_tokens,
            "temperature": overrides.temperature,
            "json_mode": overrides.json_mode,
        },
        provenance=rendered_prompt.provenance,
    )


async def plan_deliberation(
    summary: str,
    salience_scores: dict[str, Any],
    canonical_event: dict[str, Any],
    decision_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """
    A specialized, high-level workflow for Atune to decide on its next step.
    This function demonstrates a complete Render -> Call -> Parse loop.
    """
    from core.utils.net_api import ENDPOINTS, get_http_client

    scope = "atune.next_step.planning"
    spec = _resolve_spec(scope)
    episode_id = str(uuid.uuid4())

    # 1. Render the prompt
    context_dict = {
        "salience": salience_scores,
        "event": canonical_event,
        "retrieval_query": canonical_event.get("summary"),
        "decision_id": decision_id,
        "episode_id": episode_id
    }
    hint = PolicyHint(scope=scope, summary=summary, context=context_dict)
    prompt_response = await build_prompt(hint)

    # --- FIX: Wrap the entire network and parsing block in a try/except ---
    try:
        # 2. Call the LLM
        client = await get_http_client()
        payload = {
            "agent_name": prompt_response.provenance.get("agent_name", "Atune"),
            "messages": prompt_response.messages,
            "provider_overrides": prompt_response.provider_overrides,
            "provenance": prompt_response.provenance,
        }
        headers = {"x-decision-id": decision_id} if decision_id else {}
        llm_http_response = await client.post(ENDPOINTS.LLM_CALL, json=payload, headers=headers)
        
        llm_http_response.raise_for_status() # This will raise an error on 4xx/5xx responses
        llm_data = llm_http_response.json()
        llm_response = LLMResponse(
            text=llm_data.get("text"),
            json=llm_data.get("json"),
            call_id=llm_data.get("call_id"),
        )

        # 3. Parse and Validate the Response
        parsed_plan, notes = await parse_and_validate(spec, llm_response)
        final_plan = parsed_plan or {"mode": "discard", "reason": "LLM output was empty or invalid."}

    except httpx.HTTPStatusError as e:
        # Gracefully handle failures from the LLM Bus (like the 502 you received)
        final_plan = {"mode": "discard", "reason": f"Planner LLM failed with HTTP error: {e}"}
        notes = f"HTTPStatusError: {e}"
        llm_response = LLMResponse(text="", json=None, call_id=None)

    except Exception as e:
        # Catch any other unexpected errors during this process
        final_plan = {"mode": "discard", "reason": f"An unexpected error occurred in the planner: {e}"}
        notes = f"Exception: {e}"
        llm_response = LLMResponse(text="", json=None, call_id=None)


    # Attach provenance trace for debugging and learning
    final_plan["_whytrace"] = {
        "provenance": prompt_response.provenance,
        "llm_call_id": llm_response.call_id,
        "parse_notes": notes,
    }

    return final_plan, episode_id