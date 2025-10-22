# core/utils/llm_gateway_client.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

# --- New Imports for Resilience ---
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from api.endpoints.llm.call import (
    LlmCallRequest,
    LlmCallResponse,
    TaskContext,
)
from api.endpoints.llm.call import (
    ProviderOverrides as GatewayProviderOverrides,
)
from core.prompting.spec import OrchestratorResponse
from core.utils.net_api import ENDPOINTS, get_http_client

# ---------- Robust JSON extraction (remains unchanged) ----------

_CODEFENCE_RE = re.compile(
    r"```(?:\s*json\s*)?\n(?P<payload>(?:\{.*?\}|\[.*?\]))\n```",
    re.IGNORECASE | re.DOTALL,
)


def _try_load_json(blob: str) -> dict | None:
    try:
        data = json.loads(blob)
    except Exception:
        return None
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _find_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
    depth, in_str, esc = 0, False, False
    start = text.find(open_ch)
    if start < 0:
        return None
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json_flex(text: str) -> dict | None:
    if not text:
        return None
    t = text.strip()
    obj = _try_load_json(t)
    if obj is not None:
        return obj
    for m in _CODEFENCE_RE.finditer(t):
        cand = _try_load_json(m.group("payload"))
        if cand is not None:
            return cand
    for o, c in (("{", "}"), ("[", "]")):
        bal = _find_balanced(t, o, c)
        if bal:
            cand = _try_load_json(bal)
            if cand is not None:
                return cand
    try:
        i, j = t.find("{"), t.rfind("}")
        if 0 <= i < j:
            cand = _try_load_json(t[i : j + 1])
            if cand is not None:
                return cand
    except Exception:
        pass
    try:
        i, j = t.find("["), t.rfind("]")
        if 0 <= i < j:
            cand = _try_load_json(t[i : j + 1])
            if cand is not None:
                return cand
    except Exception:
        pass
    return None


# ---------- Provider overrides coercion (remains unchanged) ----------

_ALLOWED_OVERRIDE_KEYS = {"model", "temperature", "max_tokens", "json_mode", "tools"}


def _coerce_overrides(raw: dict[str, Any] | None) -> GatewayProviderOverrides:
    raw = dict(raw or {})
    cleaned: dict[str, Any] = {k: raw[k] for k in list(raw.keys()) if k in _ALLOWED_OVERRIDE_KEYS}
    tools = cleaned.get("tools")
    if isinstance(tools, list):
        safe_tools: list[dict[str, Any]] = []
        for t in tools:
            if not isinstance(t, dict):
                continue
            ttype = t.get("type")
            fn = t.get("function") if isinstance(t.get("function"), dict) else None
            if ttype == "function" and fn and isinstance(fn.get("name"), str):
                safe_tools.append(
                    {
                        "type": "function",
                        "function": {"name": fn["name"], "parameters": fn.get("parameters") or {}},
                    },
                )
        if safe_tools:
            cleaned["tools"] = safe_tools
        else:
            cleaned.pop("tools", None)
    try:
        return GatewayProviderOverrides(**cleaned)
    except Exception:
        cleaned.pop("tools", None)
        try:
            return GatewayProviderOverrides(**cleaned)
        except Exception:
            return GatewayProviderOverrides()


# ---------- Message normalization (remains unchanged) ----------


def _normalize_messages(msgs: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(msgs, str):
        return [{"role": "user", "content": msgs}]
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
        norm.append({"role": role, "content": str(content)})
    return norm


# ---------- LLM calls (MODIFIED FOR RESILIENCE AND CORRECTNESS) ----------


# This decorator adds exponential backoff to handle temporary server errors (5xx).
@retry(
    wait=wait_random_exponential(min=1, max=30),
    stop=stop_after_attempt(4),
    retry=retry_if_exception(
        lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500,
    ),
)
async def call_llm_service(
    prompt_response: OrchestratorResponse,
    agent_name: str,
    scope: str,
    arm_id: str | None = None,
    **extras: Any,
) -> LlmCallResponse:
    """
    Calls the central, Synapse-governed /llm/call endpoint with resilience.
    """
    http = await get_http_client()

    legacy_ov = extras.pop("provider_overrides", None)
    raw_overrides = getattr(prompt_response, "provider_overrides", None) or legacy_ov
    overrides = _coerce_overrides(raw_overrides)

    messages = _normalize_messages(getattr(prompt_response, "messages", []))
    task_ctx = TaskContext(scope=scope)

    # FIXED: Add explicit validation to ensure agent_name is always valid.
    # This prevents sending a bad request that would cause a 422 or 503 error.
    if not agent_name or not isinstance(agent_name, str):
        raise ValueError("'agent_name' must be a non-empty string.")

    req = LlmCallRequest(
        agent_name=agent_name,
        messages=messages,
        task_context=task_ctx,
        provider_overrides=overrides,
        provenance=getattr(prompt_response, "provenance", None),
        arm_id=arm_id,
    )

    prov = getattr(prompt_response, "provenance", None) or {}
    decision_id = prov.get("synapse_episode_id") or prov.get("episode_id") or f"ep_{uuid4().hex}"
    headers = {"x-decision-id": decision_id}

    # The `model_dump(mode="json")` is crucial for correct serialization.
    # Increased timeout for better handling of slow LLM responses.
    res = await http.post(
        ENDPOINTS.LLM_CALL,
        json=req.model_dump(mode="json"),
        headers=headers,
        timeout=120.0,
    )
    res.raise_for_status()
    return LlmCallResponse.model_validate(res.json())


@retry(
    wait=wait_random_exponential(min=1, max=30),
    stop=stop_after_attempt(3),
    retry=retry_if_exception(
        lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500,
    ),
)
async def call_llm_service_direct(
    prompt_response: OrchestratorResponse,
    agent_name: str,
    scope: str,
    **extras: Any,
) -> LlmCallResponse:
    """
    Calls the /llm/call endpoint directly with resilience (bypasses bandits/planning).
    """
    http = await get_http_client()

    legacy_ov = extras.pop("provider_overrides", None)
    raw_overrides = getattr(prompt_response, "provider_overrides", None) or legacy_ov
    overrides = _coerce_overrides(raw_overrides)

    messages = _normalize_messages(getattr(prompt_response, "messages", []))

    # FIXED: Add the same explicit validation here for consistency.
    if not agent_name or not isinstance(agent_name, str):
        raise ValueError("'agent_name' must be a non-empty string for direct calls.")

    req = LlmCallRequest(
        agent_name=agent_name,
        messages=messages,
        task_context=TaskContext(scope=scope),
        provider_overrides=overrides,
        provenance=getattr(prompt_response, "provenance", None),
    )

    headers = {"x-decision-id": f"direct_{uuid4().hex}"}
    res = await http.post(
        ENDPOINTS.LLM_CALL,
        json=req.model_dump(mode="json"),
        headers=headers,
        timeout=120.0,
    )
    res.raise_for_status()
    return LlmCallResponse.model_validate(res.json())
