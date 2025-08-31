# FINAL, CENTRALIZED, SPEC-AWARE LLM GATEWAY
from __future__ import annotations

import time
import traceback
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Body, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

# --- EcodiaOS Core Imports ---
from core.llm.call_llm import execute_llm_call
from systems.synapse.core.registry import arm_registry
from systems.synapse.schemas import TaskContext as SynapseTaskContext
from systems.synapse.sdk.client import SynapseClient

call_router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Models (modern contract)
# ──────────────────────────────────────────────────────────────────────────────


class TaskContext(BaseModel):
    scope: str = Field("generic_llm_call", example="code_review:python")
    risk: Literal["low", "medium", "high"] = Field("low")
    budget: Literal["constrained", "normal", "extended"] = Field("normal")
    purpose: str | None = Field(None, example="Refactor the user service.")


class ProviderOverrides(BaseModel):
    # Base (existing)
    json_mode: bool = Field(False)

    # New (optional) — safely merged into Synapse policy
    model: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    # Tooling/schema (adapters translate per provider downstream)
    tools: list[dict[str, Any]] | None = (
        None  # universal tool specs (OpenAI/Anthropic/Gemini translated later)
    )
    tool_choice: str | None = Field(
        default=None,
        description='One of: "auto" | "none" | "<tool_name>"',
    )
    response_json_schema: dict[str, Any] | None = None

    # Provider-specific hints (optional, ignored by others)
    gemini_cached_content: str | None = None

    # Free-form knobs for the bus/adapters
    metadata: dict[str, Any] | None = None


class LlmCallRequest(BaseModel):
    agent_name: str = Field(..., example="Simula")
    messages: list[dict[str, str]] = Field(..., example=[{"role": "user", "content": "Hello!"}])
    task_context: TaskContext = Field(default_factory=TaskContext)
    provider_overrides: ProviderOverrides = Field(default_factory=ProviderOverrides)

    # PromptSpec/Orchestrator provenance passthrough (optional)
    provenance: dict[str, Any] | None = Field(
        default=None,
        example={
            "spec_id": "simula.react.step",
            "spec_version": "1.0.0",
            "template_hash": "b3c...",
        },
    )


# ======================= RESPONSE MODELS (kept) =======================


class UsageDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    cached_tokens: int | None = 0
    audio_tokens: int | None = 0
    reasoning_tokens: int | None = 0
    accepted_prediction_tokens: int | None = 0
    rejected_prediction_tokens: int | None = 0


class Usage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: UsageDetails | None = None
    completion_tokens_details: UsageDetails | None = None


class LlmCallResponse(BaseModel):
    # Allow passing/serializing by alias so API still uses "json"
    model_config = ConfigDict(populate_by_name=True)

    text: str | None
    json_: Any | None = Field(default=None, alias="json")  # <- avoid BaseModel.json shadow
    call_id: str
    usage: Usage | None
    policy_used: dict[str, Any]
    timing_ms: dict[str, int | None]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _merge_policy(base: dict[str, Any], overrides: ProviderOverrides) -> dict[str, Any]:
    """Caller wins, but only for known safe keys."""
    merged = dict(base)
    if overrides.model:
        merged["model"] = overrides.model
    if overrides.max_tokens is not None:
        merged["max_tokens"] = int(overrides.max_tokens)
    if overrides.temperature is not None:
        merged["temperature"] = float(overrides.temperature)
    # Non-model knobs are passed through separately to the bus
    return merged


def _bus_kwargs_from_overrides(ov: ProviderOverrides) -> dict[str, Any]:
    """Translate overridable extras into bus kwargs (adapters will interpret)."""
    out: dict[str, Any] = {"json_mode": ov.json_mode}
    if ov.tools is not None:
        out["tools"] = ov.tools
    if ov.tool_choice:
        out["tool_choice"] = ov.tool_choice
    if ov.response_json_schema is not None:
        out["response_json_schema"] = ov.response_json_schema
    if ov.gemini_cached_content:
        out["gemini_cached_content"] = ov.gemini_cached_content
    if ov.metadata is not None:
        out["metadata"] = ov.metadata
    return out


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _extract_usage_tokens(usage_obj: Any) -> tuple[int, int, int]:
    """
    Normalise token counts across providers:
    usage_obj may be a dict-like payload or a pydantic model instance.
    """
    if usage_obj is None:
        return 0, 0, 0
    # Pydantic model case
    if hasattr(usage_obj, "dict"):
        u = usage_obj.dict()
    elif isinstance(usage_obj, dict):
        u = usage_obj
    else:
        # Generic object with attributes
        u = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
            "total_tokens": getattr(usage_obj, "total_tokens", 0),
        }
    pt = _safe_int(u.get("prompt_tokens", 0))
    ct = _safe_int(u.get("completion_tokens", 0))
    tt = _safe_int(u.get("total_tokens", pt + ct))
    return pt, ct, tt


# ──────────────────────────────────────────────────────────────────────────────
# API Endpoint
# ──────────────────────────────────────────────────────────────────────────────


@call_router.post(
    "/call",
    response_model=LlmCallResponse,
    summary="Centralized and Synapse-Governed LLM Gateway",
)
async def call_llm_endpoint(
    response: Response,
    request: LlmCallRequest = Body(...),
    x_budget_ms: str | None = Header(None, alias="x-budget-ms"),
    x_deadline_ts: str | None = Header(None, alias="x-deadline-ts"),
    x_decision_id: str | None = Header(None, alias="x-decision-id"),
):
    t0 = time.perf_counter()
    try:
        # 1) Synapse policy selection (arm)
        synapse_client = SynapseClient()
        synapse_task_ctx = SynapseTaskContext(
            task_key=request.task_context.scope,
            goal=request.task_context.purpose or "Generic LLM Request",
            risk_level=request.task_context.risk,
            budget=request.task_context.budget,
        )
        t_syn0 = time.perf_counter()
        selection = await synapse_client.select_arm(synapse_task_ctx, candidates=[])
        t_syn1 = time.perf_counter()

        arm = arm_registry.get_arm(selection.champion_arm.arm_id)
        if not arm:
            raise HTTPException(
                status_code=503,
                detail="Synapse failed to select a valid policy arm.",
            )

        prompt_node = next((node for node in arm.policy_graph.nodes if node.type == "prompt"), None)
        if not prompt_node:
            raise HTTPException(
                status_code=503,
                detail="Selected policy arm has no prompt configuration.",
            )

        base_policy = {
            "model": prompt_node.model,
            "temperature": prompt_node.params.get("temperature", 0.5),
            "max_tokens": prompt_node.params.get("max_tokens", 4096),
            "arm_id": arm.id,
        }
        policy = _merge_policy(base_policy, request.provider_overrides)

        # 2) Execute the call through the LLM Bus
        bus_kwargs = _bus_kwargs_from_overrides(request.provider_overrides)

        # Thread provenance/budget info to adapters/drivers
        bus_kwargs["provenance"] = request.provenance or {}
        if x_budget_ms:
            bus_kwargs.setdefault("headers", {})["x-budget-ms"] = x_budget_ms
        if x_deadline_ts:
            bus_kwargs.setdefault("headers", {})["x-deadline-ts"] = x_deadline_ts
        if x_decision_id:
            bus_kwargs.setdefault("headers", {})["x-decision-id"] = x_decision_id

        t_bus0 = time.perf_counter()
        # execute_llm_call signature should accept **bus_kwargs; unknown keys are ignored by adapters
        print("\n" + "=" * 20 + " LLM BUS CALL " + "=" * 20)
        print(f"[LLM Endpoint] Forwarding to execute_llm_call with policy: {policy}")
        print(f"[LLM Endpoint] Forwarding kwargs: {bus_kwargs}")
        print("=" * 54 + "\n")

        result = await execute_llm_call(
            messages=request.messages,
            policy=policy,
            **bus_kwargs,
        )
        t_bus1 = time.perf_counter()

        if not isinstance(result, dict) or "error" in result:
            details = (result or {}).get("details") if isinstance(result, dict) else None
            raise HTTPException(
                status_code=502,
                detail=f"LLM Provider Failed: {details or 'unknown error'}",
            )

        # 3) Timing: prefer provider-reported slice if available
        result_timing = result.get("timing_ms") if isinstance(result, dict) else None
        provider_ms_result = None
        if isinstance(result_timing, dict):
            pm = result_timing.get("provider_call_ms")
            if isinstance(pm, int | float):
                provider_ms_result = int(pm)

        provider_ms_final = (
            provider_ms_result if provider_ms_result is not None else int((t_bus1 - t_bus0) * 1000)
        )

        # 4) Normalise usage + telemetry into headers (capture what you already print)
        usage = result.get("usage")
        pt, ct, tt = _extract_usage_tokens(usage)

        # Provider/model best-effort discovery
        provider_name = (
            result.get("provider")
            or result.get("provider_name")
            or (result.get("policy_used") or {}).get("provider")
            or ""
        )
        model_name = policy.get("model") or (result.get("model") or "")

        # 5) Build the final response (unchanged schema)
        final_response = LlmCallResponse(
            text=result.get("text"),
            json_=result.get("json"),  # use internal name; serialized as "json" via alias
            call_id=selection.episode_id,
            usage=result.get("usage"),
            policy_used={
                **result.get("policy_used", {}),
                "arm_id": policy.get("arm_id"),
                "model": policy.get("model"),
                "temperature": policy.get("temperature"),
                "max_tokens": policy.get("max_tokens"),
                # Best-effort provider echo (non-breaking)
                **({"provider": provider_name} if provider_name else {}),
            },
            timing_ms={
                "synapse_select_ms": int((t_syn1 - t_syn0) * 1000),
                "provider_call_ms": provider_ms_final,
                "total_ms": int((time.perf_counter() - t0) * 1000),
            },
        )

        # 6) Observability headers (add LLM metrics so any caller can capture them)
        response.headers["X-Call-ID"] = final_response.call_id
        response.headers["X-Arm-ID"] = str(policy["arm_id"])
        response.headers["X-Provider-MS"] = str(provider_ms_final)
        response.headers["X-Cost-MS"] = str(final_response.timing_ms.get("total_ms", 0))
        # Correlation echoes (if provided inbound)
        if x_decision_id:
            response.headers["X-Decision-Id"] = x_decision_id
        if x_budget_ms:
            response.headers["X-Budget-Ms"] = x_budget_ms
        if request.provenance:
            if request.provenance.get("spec_id"):
                response.headers["X-Spec-ID"] = request.provenance.get("spec_id", "")
            if request.provenance.get("spec_version"):
                response.headers["X-Spec-Version"] = request.provenance.get("spec_version", "")
        # LLM-specific standard headers
        if provider_name:
            response.headers["X-LLM-Provider"] = str(provider_name)
        if model_name:
            response.headers["X-LLM-Model"] = str(model_name)
        response.headers["X-LLM-Prompt-Tokens"] = str(pt)
        response.headers["X-LLM-Completion-Tokens"] = str(ct)
        response.headers["X-LLM-Total-Tokens"] = str(tt)

        return final_response

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Gateway Timeout: Synapse or the LLM Provider timed out.",
        )
    except HTTPException:
        # re-raise FastAPI HTTP errors unchanged
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {type(e).__name__}: {e}",
        )
