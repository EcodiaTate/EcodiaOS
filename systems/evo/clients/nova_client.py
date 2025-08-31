# (imports as-is)
from __future__ import annotations

from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client


class NovaClient:
    """
    Nova bridge: propose → evaluate → auction, using only ENDPOINTS.
    """

    async def propose(
        self,
        brief: dict[str, Any],
        *,
        budget_ms: int | None,
        decision_id: str,
    ) -> list[dict[str, Any]]:
        http = await get_http_client()
        headers = {"x-decision-id": decision_id}
        if budget_ms is not None:
            headers["x-budget-ms"] = str(int(budget_ms))
        r = await http.post(ENDPOINTS.NOVA_PROPOSE, json=brief, headers=headers)
        r.raise_for_status()
        return list(r.json() or [])

    async def evaluate(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        http = await get_http_client()
        r = await http.post(ENDPOINTS.NOVA_EVALUATE, json=candidates)
        r.raise_for_status()
        return list(r.json() or candidates)

    async def auction(
        self,
        evaluated: list[dict[str, Any]],
        *,
        budget_ms: int | None,
        decision_id: str,
    ) -> dict[str, Any]:
        http = await get_http_client()
        headers = {"x-decision-id": decision_id}
        if budget_ms is not None:
            headers["x-budget-ms"] = str(int(budget_ms))
        r = await http.post(ENDPOINTS.NOVA_AUCTION, json=evaluated, headers=headers)
        r.raise_for_status()
        return dict(r.json() or {})

    # ---------- NEW: meta-returning variants to harvest X-Cost-MS (non-breaking) ----------
    async def propose_with_meta(
        self,
        brief: dict[str, Any],
        *,
        budget_ms: int | None,
        decision_id: str,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        http = await get_http_client()
        headers = {"x-decision-id": decision_id}
        if budget_ms is not None:
            headers["x-budget-ms"] = str(int(budget_ms))
        r = await http.post(ENDPOINTS.NOVA_PROPOSE, json=brief, headers=headers)
        r.raise_for_status()
        return list(r.json() or []), dict(r.headers)

    async def evaluate_with_meta(
        self,
        candidates: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        http = await get_http_client()
        r = await http.post(ENDPOINTS.NOVA_EVALUATE, json=candidates)
        r.raise_for_status()
        return list(r.json() or candidates), dict(r.headers)

    async def auction_with_meta(
        self,
        evaluated: list[dict[str, Any]],
        *,
        budget_ms: int | None,
        decision_id: str,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        http = await get_http_client()
        headers = {"x-decision-id": decision_id}
        if budget_ms is not None:
            headers["x-budget-ms"] = str(int(budget_ms))
        r = await http.post(ENDPOINTS.NOVA_AUCTION, json=evaluated, headers=headers)
        r.raise_for_status()
        return dict(r.json() or {}), dict(r.headers)
