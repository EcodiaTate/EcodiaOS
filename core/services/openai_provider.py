# core/services/llm/openai_provider.py
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional, Tuple

import httpx
from openai import AsyncOpenAI

# --------------------------- Config ---------------------------

_OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", os.getenv("LLM_BUS_NETWORK_TIMEOUT", "30.0")))
_OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")  # e.g. for gateways / Azure compat
_OPENAI_ORG = os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")
_OPENAI_PROJECT = os.getenv("OPENAI_PROJECT")

# ------------------------ Singletons --------------------------

_client: AsyncOpenAI | None = None
_httpx_client: httpx.AsyncClient | None = None


def _safe_messages(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Strip invalid entries and ensure non-empty minimal payload."""
    out: list[dict[str, Any]] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if role and content:
            out.append({"role": role, "content": content})
    if not out:
        out = [
            {"role": "system", "content": "You are Ecodia. Be concise and helpful."},
            {"role": "user", "content": "Hello."},
        ]
    return out


def get_openai_client() -> AsyncOpenAI:
    """Thread/async-safe lazy singleton with proxy + timeout support."""
    global _client, _httpx_client

    if _client is not None:
        return _client

    # Respect proxies if set
    proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    _httpx_client = httpx.AsyncClient(
        proxy=proxy_url,
        timeout=_OPENAI_TIMEOUT * 3,  # upstream SDK will still apply its own request timeout
    )

    _client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        organization=_OPENAI_ORG,
        project=_OPENAI_PROJECT,
        base_url=_OPENAI_BASE_URL,  # None => default
        max_retries=_OPENAI_MAX_RETRIES,
        http_client=_httpx_client,
        timeout=_OPENAI_TIMEOUT,  # request-level default; can be overridden per call
    )
    return _client


async def close_openai_client() -> None:
    """Close both the OpenAI client and the underlying HTTP client."""
    global _client, _httpx_client
    try:
        if _client is not None:
            await _client.close()
    finally:
        _client = None
        if _httpx_client is not None:
            await _httpx_client.aclose()
            _httpx_client = None


def _merge_headers(
    decision_id: str | None, kw: dict[str, Any]
) -> tuple[dict[str, str], dict[str, Any]]:
    """Non-destructively merge extra_headers; omit None decision_id."""
    extra_headers = dict(kw.pop("extra_headers", {}) or {})
    if decision_id:
        # don’t overwrite if caller already provided one
        extra_headers.setdefault("x-decision-id", decision_id)
    return extra_headers, kw


# --------------------------- API ------------------------------


async def chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str,
    decision_id: str | None = None,
    stream: bool = False,
    **kw: Any,
):
    """
    Thin wrapper over OpenAI chat.completions.create with sane defaults.

    Args:
      messages: OpenAI-style messages array.
      model: model name
      decision_id: propagated as 'x-decision-id' header when provided.
      stream: if True, returns an async iterator of events; else returns full response object.
      **kw: forwarded to openai (temperature, max_tokens, tools, tool_choice, response_format, timeout, etc.)
    """
    client = get_openai_client()
    safe_msgs = _safe_messages(messages)

    extra_headers, kw = _merge_headers(decision_id, kw)

    # Allow per-call timeout override via kw["timeout"]; fall back to client default otherwise.
    request = client.chat.completions.create(
        model=model,
        messages=safe_msgs,
        stream=stream,
        extra_headers=extra_headers,
        **kw,
    )

    if stream:
        # Expose the async generator as-is; caller is responsible for iterating/consuming.
        return request  # AsyncIterator[StreamEvent]
    else:
        return await request  # OpenAI ChatCompletion object
