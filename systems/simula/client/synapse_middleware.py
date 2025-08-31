# systems/simula/middleware/synapse_middleware.py
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from systems.simula.client.synapse_bridge import SynapseSession

ToolFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def run_tool_with_metrics(
    session: SynapseSession,
    tool_fn: ToolFn,
    params: dict[str, Any],
) -> dict[str, Any]:
    try:
        out = await tool_fn(params)
        # If your tool returns token usage or cost, pass them here:
        tokens_in = out.get("_usage", {}).get("prompt_tokens", 0)
        tokens_out = out.get("_usage", {}).get("completion_tokens", 0)
        cost = out.get("_usage", {}).get("cost_usd", 0.0)
        session.add_tool_call(ok=True, tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)
        return out
    except Exception:
        session.add_tool_call(ok=False)
        raise
