# systems/atune/budgeter/reserves.py
from __future__ import annotations

from typing import Any

from systems.atune.budgeter.manager import AttentionBudgetManager
from systems.synapse.sdk.hints_client import SynapseHintsClient


async def apply_hinted_reserves(
    budget_manager: AttentionBudgetManager,
    context: dict[str, Any],
) -> dict[str, int]:
    """
    Ask Synapse for per-event-type reserves and apply them to the budget manager.
    Expected hint format:
      { "value": { "<event_type>": <ms>, ... } }
    """
    hints = SynapseHintsClient()
    out: dict[str, int] = {}
    try:
        h = await hints.get_hint("budget", "reserves_ms", context=context)
        data = h.get("value") or {}
        if isinstance(data, dict):
            reserves = {str(k): int(v) for k, v in data.items() if isinstance(v, int | float)}
            budget_manager.set_reserves(reserves)
            out = reserves
    except Exception:
        pass
    return out
