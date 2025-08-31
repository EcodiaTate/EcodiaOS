# systems/synapse/sdk/hints_extras.py
from __future__ import annotations

from typing import Any

try:
    # Uses your existing hints client if available
    from systems.synapse.sdk.hints_client import SynapseHintsClient  # type: ignore
except Exception:
    SynapseHintsClient = None  # type: ignore


class HintsExtras:
    """
    Thin convenience around SynapseHintsClient for common Atune planners:
      - conformal/alpha_per_head: {head_name: alpha}
      - planner/price_per_capability: {capability: unit_cost_multiplier}
    """

    async def alpha_per_head(
        self,
        default: float = 0.1,
        context: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        if SynapseHintsClient is None:
            return {}
        try:
            h = await SynapseHintsClient().get_hint(
                "conformal",
                "alpha_per_head",
                context=context or {},
            )
            raw = h.get("value") or h
            out: dict[str, float] = {}
            for k, v in dict(raw or {}).items():
                try:
                    out[str(k)] = max(1e-6, min(0.5, float(v)))
                except Exception:
                    continue
            return out
        except Exception:
            return {}

    async def price_per_capability(
        self,
        context: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        if SynapseHintsClient is None:
            return {}
        try:
            h = await SynapseHintsClient().get_hint(
                "planner",
                "price_per_capability",
                context=context or {},
            )
            raw = h.get("value") or h
            return {str(k): float(v) for k, v in dict(raw or {}).items()}
        except Exception:
            return {}
