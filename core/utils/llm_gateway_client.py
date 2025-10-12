# core/utils/llm_gateway_client.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

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

# ---------- Robust JSON extraction (exported) ----------

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
    """
    Best-effort JSON extraction:
      1) Direct parse (whole string)
      2) ```json ...``` or ``` ...``` fenced blocks (first match wins)
      3) First balanced {...} or [...] slice
      4) First/last brace slice as last resort
    Returns a dict, or first dict element if top-level is a list of dicts.
    """
    if not text:
        return None

    t = text.strip()

    # 1) Direct parse
    obj = _try_load_json(t)
    if obj is not None:
        return obj

    # 2) Fenced blocks (use the first that parses)
    for m in _CODEFENCE_RE.finditer(t):
        cand = _try_load_json(m.group("payload"))
        if cand is not None:
            return cand

    # 3) Balanced slice
    for o, c in (("{", "}"), ("[", "]")):
        bal = _find_balanced(t, o, c)
        if bal:
            cand = _try_load_json(bal)
            if cand is not None:
                return cand

    # 4) Fallback: first '{' to last '}' (or '['..']')
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


# ---------- Provider overrides coercion ----------

_ALLOWED_OVERRIDE_KEYS = {"model", "temperature", "max_tokens", "json_mode", "tools"}


def _coerce_overrides(raw: dict[str, Any] | None) -> GatewayProviderOverrides:
    """
    Safely build gateway ProviderOverrides from orchestrator dict.
    - Drops unknown keys
    - Sanitizes 'tools' to the minimal shape the gateway expects (if present)
    - Falls back gracefully if validation fails
    """
    raw = dict(raw or {})
    cleaned: dict[str, Any] = {k: raw[k] for k in list(raw.keys()) if k in _ALLOWED_OVERRIDE_KEYS}

    # tools: keep only known keys if present (shape can vary per gateway; keep minimal)
    tools = cleaned.get("tools")
    if isinstance(tools, list):
        safe_tools: list[dict[str, Any]] = []
        for t in tools:
            if not isinstance(t, dict):
                continue
            # Accept OpenAI-style function tools minimally
            ttype = t.get("type")
            fn = t.get("function") if isinstance(t.get("function"), dict) else None
            if ttype == "function" and fn and isinstance(fn.get("name"), str):
                safe_tools.append(
                    {
                        "type": "function",
                        "function": {"name": fn["name"], "parameters": fn.get("parameters") or {}},
                    }
                )
        if safe_tools:
            cleaned["tools"] = safe_tools
        else:
            cleaned.pop("tools", None)

    try:
        return GatewayProviderOverrides(**cleaned)
    except Exception:
        # Last resort: drop tools and retry
        cleaned.pop("tools", None)
        try:
            return GatewayProviderOverrides(**cleaned)
        except Exception:
            # Absolute fallback: empty overrides
            return GatewayProviderOverrides()


# ---------- Message normalization ----------


def _normalize_messages(msgs: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Accepts either a string (treated as a single 'user' message) or
    a list of role/content dicts. Ensures 'content' is a string.
    """
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
        norm.append({"role": role, "content": content})
    return norm


# ---------- LLM calls ----------
# --- change signatures to accept extras and coalesce provider_overrides ---


async def call_llm_service(
    prompt_response: OrchestratorResponse,
    agent_name: str,
    scope: str,
    **extras: Any,  # ← accept unknown kwargs
) -> LlmCallResponse:
    """
    Calls the central, Synapse-governed /call endpoint (policy-aware).
    """
    http = await get_http_client()

    # Back-compat: allow callers to pass provider_overrides as a kwarg
    legacy_ov = extras.pop("provider_overrides", None)
    # Prefer the one already in prompt_response; else use legacy kwarg
    raw_overrides = getattr(prompt_response, "provider_overrides", None) or legacy_ov
    overrides = _coerce_overrides(raw_overrides)

    # Normalize messages (if some callers pass raw strings/objects)
    messages = _normalize_messages(getattr(prompt_response, "messages", []))

    task_ctx = TaskContext(scope=scope)
    req = LlmCallRequest(
        agent_name=agent_name,
        messages=messages,
        task_context=task_ctx,
        provider_overrides=overrides,
        provenance=getattr(prompt_response, "provenance", None),
    )

    prov = getattr(prompt_response, "provenance", None) or {}
    decision_id = prov.get("synapse_episode_id") or prov.get("episode_id") or f"ep_{uuid4().hex}"
    headers = {"x-decision-id": decision_id}

    res = await http.post(
        ENDPOINTS.LLM_CALL,
        json=req.model_dump(mode="json", by_alias=True),
        headers=headers,
        timeout=60.0,
    )
    res.raise_for_status()
    return LlmCallResponse.model_validate(res.json())


async def call_llm_service_direct(
    prompt_response: OrchestratorResponse,
    agent_name: str,
    scope: str,
    **extras: Any,  # ← accept unknown kwargs here too
) -> LlmCallResponse:
    """
    Calls the /llm/call endpoint directly (bypasses bandits/planning).
    Useful for critics, scorers, deterministic utilities.
    """
    http = await get_http_client()

    legacy_ov = extras.pop("provider_overrides", None)
    raw_overrides = getattr(prompt_response, "provider_overrides", None) or legacy_ov
    overrides = _coerce_overrides(raw_overrides)

    messages = _normalize_messages(getattr(prompt_response, "messages", []))

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
        json=req.model_dump(mode="json", by_alias=True),
        headers=headers,
        timeout=60.0,
    )
    res.raise_for_status()
    return LlmCallResponse.model_validate(res.json())
