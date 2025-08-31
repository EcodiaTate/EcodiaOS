# systems/synapse/sdk/hints_client.py
from __future__ import annotations

from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client


class SynapseHintsClient:
    """
    Fetch per-cycle tuning hints from Synapse (e.g., leak_gamma).
    Expects ENDPOINTS to expose SYNAPSE_HINT dynamically at startup.
    Contract (POST):
      req:  { "namespace": "<str>", "key": "<str>", "context": { ... } }
      resp: { "value": <any>, "meta": { ... } }
    """

    async def get_hint(
        self,
        namespace: str,
        key: str,
        context: dict[str, Any] | None = None,
        budget_ms: int = 120,
    ) -> dict[str, Any]:
        client = await get_http_client()
        r = await client.post(
            ENDPOINTS.SYNAPSE_HINT,
            json={"namespace": namespace, "key": key, "context": context or {}},
            headers={"x-budget-ms": str(budget_ms)},
        )
        r.raise_for_status()
        return r.json()

    async def get_float(
        self,
        namespace: str,
        key: str,
        default: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> float | None:
        try:
            out = await self.get_hint(namespace, key, context=context)
            v = out.get("value", default)
            return float(v) if v is not None else default
        except Exception:
            return default
