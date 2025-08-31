from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .context import get_ctx


def _infer_service_hint(url_path: str) -> str | None:
    # cheap path-based hints to namespace X-Cost-MS
    if url_path.endswith("/llm/call"):
        return "llm"
    if url_path.endswith("/nova/propose"):
        return "nova.propose"
    if url_path.endswith("/nova/evaluate"):
        return "nova.evaluate"
    if url_path.endswith("/nova/auction"):
        return "nova.auction"
    if "/axon/core/act" in url_path:
        return "axon.act"
    return None


def instrument_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """
    Attaches request/response hooks for correlation + metrics harvest.
    Idempotent: safe to call multiple times.
    """

    async def _on_request(request: httpx.Request):
        ctx = get_ctx()
        if not ctx.enabled:
            return
        # inject correlation we already know; allow callers to set their own headers beforehand
        to_add = ctx.note_request(
            decision_id=ctx.correlation.get("decision_id"),
            budget_ms=ctx.correlation.get("budget_ms"),
            spec_id=ctx.correlation.get("spec_id"),
            spec_version=ctx.correlation.get("spec_version"),
            arm_id=ctx.correlation.get("arm_id"),
        )
        for k, v in to_add.items():
            if k not in request.headers:
                request.headers[k] = v

    async def _on_response(response: httpx.Response):
        ctx = get_ctx()
        if not ctx.enabled:
            return
        path = urlparse(str(response.request.url)).path
        ctx.note_response(dict(response.headers), service_hint=_infer_service_hint(path))

    # Avoid duplicate registration
    hooks = client.event_hooks
    if _on_request not in hooks.get("request", []):
        hooks.setdefault("request", []).append(_on_request)
    if _on_response not in hooks.get("response", []):
        hooks.setdefault("response", []).append(_on_response)
    return client
