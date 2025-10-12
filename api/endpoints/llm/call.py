# core/api/llm/call.py  (FINAL, CENTRALIZED, SPEC-AWARE LLM GATEWAY)
from __future__ import annotations

import json
import time
import traceback
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Body, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

# --- EcodiaOS Core Imports ---
from core.llm.call_llm import execute_llm_call
from core.services.synapse import synapse
from systems.synapse.core.registry import arm_registry
from systems.synapse.schemas import TaskContext as SynapseTaskContext

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

    # Safe model knobs
    model: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    # Tooling/schema (adapters translate per provider downstream)
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | None = Field(
        default=None, description='One of: "auto" | "none" | "<tool_name>"'
    )
    response_json_schema: dict[str, Any] | None = None

    # Provider-specific hints (optional, ignored by others)
    gemini_cached_content: str | None = None

    # Free-form knobs for the bus/adapters
    metadata: dict[str, Any] | None = None


class LlmCallRequest(BaseModel):
    agent_name: str = Field(..., example="Simula")
    messages: list[dict[str, Any]] = Field(..., example=[{"role": "user", "content": "Hello!"}])
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
    if hasattr(usage_obj, "dict"):
        u = usage_obj.dict()
    elif isinstance(usage_obj, dict):
        u = usage_obj
    else:
        u = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
            "total_tokens": getattr(usage_obj, "total_tokens", 0),
        }
    pt = _safe_int(u.get("prompt_tokens", 0))
    ct = _safe_int(u.get("completion_tokens", 0))
    tt = _safe_int(u.get("total_tokens", pt + ct))
    return pt, ct, tt


def _normalize_messages(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Ensure role/content exist and content is a string.
    """
    norm: list[dict[str, Any]] = []
    for m in msgs or []:
        role = m.get("role") or "user"
        content = m.get("content")
        if isinstance(content, (dict, list)):
            try:
                content = json.dumps(content, ensure_ascii=False)
            except Exception:
                content = str(content)
        elif content is None:
            content = ""
        norm.append({"role": role, "content": content})
    return norm


def _merge_policy(base: dict[str, Any], overrides: ProviderOverrides) -> dict[str, Any]:
    """
    Correct precedence: defaults/dynamic/arm -> caller overrides (known keys only).
    """
    merged = dict(base)
    if overrides.model:
        merged["model"] = overrides.model
    if overrides.max_tokens is not None:
        merged["max_tokens"] = int(overrides.max_tokens)
    if overrides.temperature is not None:
        merged["temperature"] = float(overrides.temperature)
    return merged


def _bus_kwargs_from_overrides(ov: ProviderOverrides) -> dict[str, Any]:
    """
    Translate overridable extras into bus kwargs (adapters will interpret).
    """
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


def _extract_prompt_from_arm(arm_obj: Any) -> tuple[str, float, int]:
    """
    Supports both registry objects and raw JSON stored on the arm.
    Returns (model, temperature, max_tokens).
    """
    # 1) If registry arm has a structured policy_graph with nodes
    try:
        nodes = getattr(getattr(arm_obj, "policy_graph", None), "nodes", None)
        if isinstance(nodes, list) and nodes:
            for n in nodes:
                # n may be a pydantic object with attrs or a dict
                n_type = getattr(n, "type", None) if not isinstance(n, dict) else n.get("type")
                if n_type == "prompt":
                    model = getattr(n, "model", None) if not isinstance(n, dict) else n.get("model")
                    params = (
                        getattr(n, "params", None)
                        if not isinstance(n, dict)
                        else n.get("params", {}) or {}
                    )
                    temp = float(params.get("temperature", 0.7))
                    toks = int(params.get("max_tokens", 4096))
                    if model:
                        return model, temp, toks
    except Exception:
        pass

    # 2) Try policy_graph_json (string) or policy_graph as JSON string
    for attr in ("policy_graph_json", "policy_graph"):
        raw = getattr(arm_obj, attr, None)
        if isinstance(raw, str) and raw.strip().startswith("{"):
            try:
                pg = json.loads(raw)
                for n in pg.get("nodes") or []:
                    if n.get("type") == "prompt":
                        model = n.get("model")
                        params = n.get("params") or {}
                        temp = float(params.get("temperature", 0.7))
                        toks = int(params.get("max_tokens", 4096))
                        if model:
                            return model, temp, toks
            except Exception:
                continue

    # 3) Absolute fallback
    return "gpt-4o-mini", 0.7, 4096


def _extract_llm_cfg_from_dynamic(champ_content: Any) -> dict[str, Any]:
    """
    Planner payloads might use 'llm_config' or 'llm_call' shape.
    """
    if isinstance(champ_content, dict):
        if isinstance(champ_content.get("llm_config"), dict):
            return champ_content["llm_config"]
        if isinstance(champ_content.get("llm_call"), dict):
            return champ_content["llm_call"]
    return {}


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
        synapse_task_ctx = SynapseTaskContext(
            task_key=request.task_context.scope,
            goal=request.task_context.purpose or "Generic LLM Request",
            risk_level=request.task_context.risk,
            budget=request.task_context.budget,
            metadata={},  # optional: carry request.provenance here if helpful
        )

        # 1) Selection (policy/arm or dynamic plan)
        t_syn0 = time.perf_counter()
        selection = await synapse.select_or_plan(synapse_task_ctx, candidates=[])
        t_syn1 = time.perf_counter()

        champ = selection.champion_arm
        arm_id = champ.arm_id if champ else ""
        arm = arm_registry.get_arm(arm_id)  # may be None for dynamic LLM-plans

        # 2) Resolve base policy from dynamic plan or PolicyArm
        if champ and champ.content:
            # Dynamic LLM-plan path
            llm_cfg = _extract_llm_cfg_from_dynamic(champ.content)
            base_policy = {
                "model": llm_cfg.get("model", "gpt-4o-mini"),
                "temperature": llm_cfg.get("temperature", 0.7),
                "max_tokens": llm_cfg.get("max_tokens", 4096),
                "arm_id": arm_id or "dyn::planner",
            }
        else:
            # PolicyArm path
            if not arm:
                raise HTTPException(
                    status_code=503, detail="Synapse selected a missing policy arm."
                )
            model, temp, toks = _extract_prompt_from_arm(arm)
            base_policy = {
                "model": model,
                "temperature": temp,
                "max_tokens": toks,
                "arm_id": getattr(arm, "id", arm_id),
            }

        # 3) Caller overrides (known-safe keys only)
        policy = _merge_policy(base_policy, request.provider_overrides)

        # 4) Bus kwargs: tools/schema/etc.
        bus_kwargs = _bus_kwargs_from_overrides(request.provider_overrides)
        bus_kwargs["provenance"] = request.provenance or {}

        if x_budget_ms:
            bus_kwargs.setdefault("headers", {})["x-budget-ms"] = x_budget_ms
        if x_deadline_ts:
            bus_kwargs.setdefault("headers", {})["x-deadline-ts"] = x_deadline_ts
        if x_decision_id:
            bus_kwargs.setdefault("headers", {})["x-decision-id"] = x_decision_id

        # 5) Execute provider call
        messages = _normalize_messages(request.messages)

        t_bus0 = time.perf_counter()
        print("\n" + "=" * 20 + " LLM BUS CALL " + "=" * 20)
        print(f"[LLM Endpoint] Forwarding to execute_llm_call with policy: {policy}")
        print("=" * 54 + "\n")

        result = await execute_llm_call(messages=messages, policy=policy, **bus_kwargs)
        t_bus1 = time.perf_counter()

        if not isinstance(result, dict) or "error" in result:
            details = (result or {}).get("details") if isinstance(result, dict) else None
            raise HTTPException(
                status_code=502, detail=f"LLM Provider Failed: {details or 'unknown error'}"
            )

        # 6) Timing / usage
        result_timing = result.get("timing_ms") if isinstance(result, dict) else None
        provider_ms_result: int | None = None
        if isinstance(result_timing, dict):
            pm = result_timing.get("provider_call_ms")
            if isinstance(pm, (int, float)):
                provider_ms_result = int(pm)
        provider_ms_final = (
            provider_ms_result if provider_ms_result is not None else int((t_bus1 - t_bus0) * 1000)
        )

        usage = result.get("usage")
        pt, ct, tt = _extract_usage_tokens(usage)

        provider_name = (
            result.get("provider")
            or result.get("provider_name")
            or (result.get("policy_used") or {}).get("provider")
            or ""
        )
        model_name = policy.get("model") or (result.get("model") or "")

        # 7) Build response
        final_response = LlmCallResponse(
            text=result.get("text"),
            json_=result.get("json"),
            call_id=selection.episode_id,
            usage=result.get("usage"),
            policy_used={
                **(result.get("policy_used") or {}),
                "arm_id": policy.get("arm_id"),
                "model": policy.get("model"),
                "temperature": policy.get("temperature"),
                "max_tokens": policy.get("max_tokens"),
                **({"provider": provider_name} if provider_name else {}),
            },
            timing_ms={
                "synapse_select_ms": int((t_syn1 - t_syn0) * 1000),
                "provider_call_ms": provider_ms_final,
                "total_ms": int((time.perf_counter() - t0) * 1000),
            },
        )

        # 8) Observability headers
        response.headers["X-Call-ID"] = final_response.call_id
        response.headers["X-Arm-ID"] = str(policy["arm_id"])
        response.headers["X-Provider-MS"] = str(provider_ms_final)
        response.headers["X-Cost-MS"] = str(final_response.timing_ms.get("total_ms", 0))
        if x_decision_id:
            response.headers["X-Decision-Id"] = x_decision_id
        if x_budget_ms:
            response.headers["X-Budget-Ms"] = x_budget_ms
        if request.provenance:
            if request.provenance.get("spec_id"):
                response.headers["X-Spec-ID"] = request.provenance.get("spec_id", "")
            if request.provenance.get("spec_version"):
                response.headers["X-Spec-Version"] = request.provenance.get("spec_version", "")
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
            status_code=504, detail="Gateway Timeout: Synapse or the LLM Provider timed out."
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Internal Server Error: {type(e).__name__}: {e}"
        )
