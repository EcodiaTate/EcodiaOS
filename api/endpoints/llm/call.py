# core/api/llm/call.py  (FINAL, CENTRALIZED, SPEC-AWARE LLM GATEWAY)
from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass
from typing import Any, Literal, Optional, Tuple
from uuid import uuid4

import httpx
from fastapi import APIRouter, Body, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

# --- EcodiaOS Core Imports ---
from core.llm.call_llm import execute_llm_call
from core.services.synapse import synapse
from core.utils.neo.cypher_query import cypher_query
from systems.synapse.schemas import (
    ArmScore,
    SelectArmResponse,
)
from systems.synapse.schemas import (
    TaskContext as SynapseTaskContext,
)

call_router = APIRouter()

# ------------------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------------------
log = logging.getLogger(__name__)


def _short(obj: Any, limit: int = 500) -> str:
    """Stringify and hard-truncate for safe logging."""
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)  # type: ignore[arg-type]
    except Exception:
        s = str(obj)
    return (s[:limit] + "…") if len(s) > limit else s


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
    Supports registry-like objects and raw JSON stored on the arm.
    Returns (model, temperature, max_tokens).
    """
    # 1) If arm has a structured policy_graph with nodes
    try:
        nodes = getattr(getattr(arm_obj, "policy_graph", None), "nodes", None)
        if isinstance(nodes, list) and nodes:
            for n in nodes:
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
    except Exception as e:
        log.debug("[LLM Endpoint] policy_graph.nodes extraction failed: %r", e, exc_info=True)

    # 2) Try policy_graph_json or policy_graph as JSON string
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
            except Exception as e:
                log.debug("[LLM Endpoint] JSON policy_graph parse failed (%s): %r", attr, e)

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
    messages: list[dict[str, Any]] = Field(..., example=[{"role": "user", "content": "Hello!"}])
    task_context: TaskContext = Field(default_factory=TaskContext)
    provider_overrides: ProviderOverrides = Field(default_factory=ProviderOverrides)
    provenance: dict[str, Any] | None = Field(
        default=None,
        example={
            "spec_id": "simula.react.step",
            "spec_version": "1.0.0",
            "template_hash": "b3c...",
        },
    )
    # MODIFIED: Accept an optional arm_id to bypass Synapse selection
    arm_id: str | None = Field(
        default=None,
        description="Directly specify a policy arm to use, bypassing Synapse selection.",
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
# Synapse helpers (DB-backed arm fetch)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class _ArmRow:
    id: str
    mode: str
    policy_graph: dict | str | None  # we’ll accept either; extractor handles both


async def _fetch_arm_from_db(arm_id: str) -> _ArmRow | None:
    """
    Definitive resolver: read PolicyArm straight from Neo4j.
    - Accepts either p.id or p.arm_id (some writers used one or the other).
    - Returns a minimal object with id/mode/policy_graph.
    - policy_graph may be JSON string or already a dict; downstream code supports both.
    """
    if not arm_id:
        return None

    rows = (
        await cypher_query(
            """
        MATCH (p:PolicyArm)
        WHERE coalesce(p.id, p.arm_id) = $id
        RETURN
          coalesce(p.id, p.arm_id)     AS id,
          coalesce(p.mode, 'generic')  AS mode,
          p.policy_graph               AS policy_graph
        LIMIT 1
        """,
            {"id": arm_id},
        )
        or []
    )

    if not rows:
        return None

    r = rows[0]
    pid = (r.get("id") or "").strip()
    if not pid:
        return None

    pg = r.get("policy_graph")
    # If policy_graph is a JSON string, leave it as is; _extract_prompt_from_arm handles it.
    # If it is already a dict (some legacy writers stored a map), keep it too.
    # If it’s None, leave None – extractor will fall back to DEFAULT.
    mode = (r.get("mode") or "generic").strip()

    return _ArmRow(id=pid, mode=mode, policy_graph=pg)


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
    # Correlation IDs
    call_uuid = uuid4().hex
    t0 = time.perf_counter()

    # Pre-flight observability
    try:
        msg_preview = [
            {"role": m.get("role"), "len": len(m.get("content") or "")}
            for m in (request.messages or [])
        ]
        log.info(
            "[LLM Endpoint] ▶ call start | call_id=%s agent=%s scope=%s risk=%s budget=%s msgs=%d headers(budget_ms=%s, deadline_ts=%s, decision_id=%s)",
            call_uuid,
            request.agent_name,
            request.task_context.scope,
            request.task_context.risk,
            request.task_context.budget,
            len(request.messages or []),
            x_budget_ms,
            x_deadline_ts,
            x_decision_id,
        )
        log.debug(
            "[LLM Endpoint] request.preview | msgs_preview=%s provenance=%s overrides=%s arm_id=%s",
            _short(msg_preview, 1000),
            _short(request.provenance, 800),
            _short(request.provider_overrides.model_dump(exclude_none=True), 800),
            request.arm_id,
        )
    except Exception as e:
        log.warning("[LLM Endpoint] request logging failed: %r", e, exc_info=True)

    try:
        selection: SelectArmResponse
        t_syn0 = time.perf_counter()

        # --- MODIFIED LOGIC: Two paths for arm selection ---
        if request.arm_id:
            # PATH 1: Direct arm specified, bypass Synapse selection but resolve via DB.
            log.info(
                "[LLM Endpoint] arm override provided; bypassing Synapse selection | arm_id=%s",
                request.arm_id,
            )
            arm = await _fetch_arm_from_db(request.arm_id)
            if not arm:
                log.error(
                    "[LLM Endpoint] 422 arm not found in DB | requested=%s",
                    request.arm_id,
                )
                raise HTTPException(
                    status_code=422,
                    detail=f"The specified arm_id '{request.arm_id}' was not found in the database.",
                )
            # Create a synthetic selection response for downstream consistency.
            selection = SelectArmResponse(
                episode_id=f"direct_{call_uuid}",
                champion_arm=ArmScore(arm_id=request.arm_id, score=1.0, reason="Direct selection"),
                shadow_arms=[],
            )
            t_syn1 = time.perf_counter()

        else:
            # PATH 2: Synapse selection (DB-backed)
            synapse_task_ctx = SynapseTaskContext(
                task_key=request.task_context.scope,
                goal=request.task_context.purpose or "Generic LLM Request",
                risk_level=request.task_context.risk,
                budget=request.task_context.budget,
                metadata=request.provenance or {},
            )
            log.info(
                "[LLM Endpoint] selecting arm via Synapse | task_key=%s goal=%s risk=%s budget=%s",
                synapse_task_ctx.task_key,
                _short(synapse_task_ctx.goal, 200),
                synapse_task_ctx.risk_level,
                synapse_task_ctx.budget,
            )
            try:
                selection = await synapse.select_or_plan(synapse_task_ctx, candidates=[])
            except Exception as e:
                # This is often the root of 503 cascades—log very verbosely
                log.exception("[LLM Endpoint] Synapse.select_or_plan failed | %r", e)
                raise HTTPException(
                    status_code=503, detail=f"Synapse selection failed: {type(e).__name__}: {e}",
                )
            t_syn1 = time.perf_counter()

        # --- From here, the logic is unified ---
        champ = selection.champion_arm
        arm_id = champ.arm_id if champ else ""

        # 2) Resolve base policy from dynamic plan or DB-backed static PolicyArm
        if champ and getattr(champ, "content", None):
            # Dynamic LLM-plan path (only from Synapse)
            llm_cfg = _extract_llm_cfg_from_dynamic(champ.content)
            base_policy = {
                "model": llm_cfg.get("model", "gpt-4o-mini"),
                "temperature": llm_cfg.get("temperature", 0.7),
                "max_tokens": llm_cfg.get("max_tokens", 4096),
                "arm_id": arm_id or "dyn::planner",
            }
            log.info(
                "[LLM Endpoint] dynamic plan selected | arm_id=%s model=%s temp=%s max_tokens=%s",
                base_policy["arm_id"],
                base_policy["model"],
                base_policy["temperature"],
                base_policy["max_tokens"],
            )
            log.debug("[LLM Endpoint] planner.llm_cfg=%s", _short(llm_cfg, 1000))
        else:
            # Static PolicyArm path — fetch arm from DB
            if not arm_id:
                log.error("[LLM Endpoint] 503 no arm_id resolved from selection")
                raise HTTPException(
                    status_code=503,
                    detail="Policy arm not provided or resolved.",
                )

            arm = await _fetch_arm_from_db(arm_id)
            if not arm:
                log.error(
                    "[LLM Endpoint] 503 selected arm missing in DB | selected=%s",
                    arm_id,
                )
                raise HTTPException(
                    status_code=503,
                    detail=f"Policy arm '{arm_id}' selected by Synapse but not found in the database.",
                )

            model, temp, toks = _extract_prompt_from_arm(arm)
            base_policy = {
                "model": model,
                "temperature": temp,
                "max_tokens": toks,
                "arm_id": getattr(arm, "id", arm_id),
            }
            log.info(
                "[LLM Endpoint] static arm selected | arm_id=%s model=%s temp=%s max_tokens=%s",
                base_policy["arm_id"],
                model,
                temp,
                toks,
            )

        # 3) Caller overrides (known-safe keys only)
        policy = _merge_policy(base_policy, request.provider_overrides)
        if policy != base_policy:
            log.info("[LLM Endpoint] overrides applied | final_policy=%s", policy)
        else:
            log.debug("[LLM Endpoint] no overrides applied | policy=%s", policy)

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

        # Log message metrics, not contents (avoid PII/size blowups)
        total_char = sum(len(m.get("content", "")) for m in messages)
        log.info(
            "[LLM Endpoint] ▶ provider call | model=%s temp=%s max_tokens=%s msgs=%d chars=%d",
            policy.get("model"),
            policy.get("temperature"),
            policy.get("max_tokens"),
            len(messages),
            total_char,
        )
        log.debug("[LLM Endpoint] bus_kwargs=%s", _short(bus_kwargs, 1200))

        t_bus0 = time.perf_counter()
        result = await execute_llm_call(messages=messages, policy=policy, **bus_kwargs)
        t_bus1 = time.perf_counter()

        if not isinstance(result, dict) or "error" in result:
            details = (result or {}).get("details") if isinstance(result, dict) else None
            log.error(
                "[LLM Endpoint] 502 provider error | details=%s raw=%s",
                details,
                _short(result, 1200),
            )
            raise HTTPException(
                status_code=502,
                detail=f"LLM Provider Failed: {details or 'unknown error'}",
            )

        # 6) Timing / usage
        provider_ms_final = (result.get("timing_ms", {}) or {}).get(
            "provider",
            int((t_bus1 - t_bus0) * 1000),
        )
        usage = result.get("usage")
        pt, ct, tt = _extract_usage_tokens(usage)
        model_name = policy.get("model") or (result.get("model") or "")

        log.info(
            "[LLM Endpoint] ◀ provider ok | model=%s provider_ms=%s tokens(p=%s c=%s t=%s)",
            model_name,
            provider_ms_final,
            pt,
            ct,
            tt,
        )
        log.debug(
            "[LLM Endpoint] provider.result.preview | text_len=%s json_keys=%s timing=%s",
            len(result.get("text") or "") if result.get("text") else 0,
            list((result.get("json") or {}).keys())
            if isinstance(result.get("json"), dict)
            else type(result.get("json")).__name__,
            _short(result.get("timing_ms", {}), 500),
        )

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
            },
            timing_ms={
                "synapse_select_ms": int((t_syn1 - t_syn0) * 1000),
                "provider_call_ms": provider_ms_final,
                "total_ms": int((time.perf_counter() - t0) * 1000),
            },
        )

        # 8) Observability headers
        response.headers["X-Call-ID"] = final_response.call_id
        response.headers["X-Arm-ID"] = str(policy.get("arm_id", "unknown"))
        response.headers["X-Provider-MS"] = str(provider_ms_final)
        response.headers["X-Cost-MS"] = str(final_response.timing_ms.get("total_ms", 0))
        if x_decision_id:
            response.headers["X-Decision-Id"] = x_decision_id
        if model_name:
            response.headers["X-LLM-Model"] = str(model_name)
        response.headers["X-LLM-Prompt-Tokens"] = str(pt)
        response.headers["X-LLM-Completion-Tokens"] = str(ct)
        response.headers["X-LLM-Total-Tokens"] = str(tt)

        log.info(
            "[LLM Endpoint] ✔ call ok | call_id=%s total_ms=%s synapse_ms=%s provider_ms=%s arm_id=%s",
            final_response.call_id,
            final_response.timing_ms["total_ms"],
            final_response.timing_ms["synapse_select_ms"],
            final_response.timing_ms["provider_ms"]
            if "provider_ms" in final_response.timing_ms
            else final_response.timing_ms["provider_call_ms"],
            policy.get("arm_id"),
        )
        return final_response

    except httpx.TimeoutException:
        log.error("[LLM Endpoint] 504 timeout | call_id=%s", call_uuid, exc_info=True)
        raise HTTPException(
            status_code=504,
            detail="Gateway Timeout: Synapse or the LLM Provider timed out.",
        )
    except HTTPException as he:
        # Bubble, but scream first
        log.error(
            "[LLM Endpoint] HTTPException | status=%s detail=%s call_id=%s",
            he.status_code,
            getattr(he, "detail", None),
            call_uuid,
        )
        raise
    except Exception as e:
        # Absolute last-resort catcher—show full trace
        log.exception("[LLM Endpoint] 500 crash | call_id=%s", call_uuid)
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {type(e).__name__}: {e}",
        )
