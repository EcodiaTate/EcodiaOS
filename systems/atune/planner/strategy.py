# systems/atune/planner/strategy.py
from __future__ import annotations

import os
from typing import Any

from systems.synapse.sdk.hints_client import SynapseHintsClient


async def resolve_market_strategy(
    default_env: str = "ATUNE_MARKET_STRATEGY",
    context: dict[str, Any] | None = None,
) -> str:
    """
    Prefer Synapse hint 'planner/market_strategy'; fallback to env; else 'vcg'.
    """
    try:
        h = await SynapseHintsClient().get_hint("planner", "market_strategy", context=context or {})
        val = h.get("value")
        if isinstance(val, str) and val:
            return val
    except Exception:
        pass
    return os.getenv(default_env, "vcg")
