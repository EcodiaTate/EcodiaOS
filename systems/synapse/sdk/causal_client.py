# systems/synapse/sdk/causal_client.py
from __future__ import annotations

from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client


class SynapseCausalClient:
    """
    Retrieves SCM snapshots produced by Synapse (analytics/learning lives there).
    Expects ENDPOINTS.SYNAPSE_SCM_SNAPSHOT.
    Contract (GET):
      query: ?domain=<string>&version=<optional>
      resp:  { "domain": "...", "version": "...", "graph": {...}, "hash": "...", "created_utc": "..." }
    """

    async def get_scm_snapshot(
        self,
        domain: str,
        version: str | None = None,
        budget_ms: int = 200,
    ) -> dict[str, Any] | None:
        client = await get_http_client()
        url = ENDPOINTS.SYNAPSE_SCM_SNAPSHOT
        params = {"domain": domain}
        if version:
            params["version"] = version
        r = await client.get(url, params=params, headers={"x-budget-ms": str(budget_ms)})
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("graph"):
            return data
        return None
