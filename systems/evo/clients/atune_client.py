# file: systems/evo/clients/atune_client.py
from __future__ import annotations

from hashlib import blake2s
from typing import Any

from pydantic import BaseModel

from core.utils.net_api import ENDPOINTS, get_http_client  # overlay + shared client


def _hash16(obj: object) -> str:
    return blake2s(repr(obj).encode("utf-8")).hexdigest()[:16]


class AtuneClient(BaseModel):
    """
    Atune client bound to the OpenAPI overlay:
    - All paths resolved via ENDPOINTS.*
    - Single ingress: route/cognitive_cycle (Unity only via Atune).
    """

    # ------------------------ Meta -----------------------------------------
    async def meta_status(self) -> dict[str, Any]:
        client = await get_http_client()
        r = await client.get(ENDPOINTS.ATUNE_META_STATUS)
        r.raise_for_status()
        return dict(r.json())

    async def meta_endpoints(self) -> dict[str, Any]:
        client = await get_http_client()
        r = await client.get(ENDPOINTS.ATUNE_META_ENDPOINTS)
        r.raise_for_status()
        return dict(r.json())

    # ------------------------ Tracing --------------------------------------
    async def get_trace(self, decision_id: str) -> dict[str, Any]:
        """
        Overlay should expose either a templated or base path. Handle both.
        """
        base = ENDPOINTS.ATUNE_TRACE
        if "{decision_id}" in base:
            url = base.replace("{decision_id}", decision_id)
        elif base.endswith("/"):
            url = base + decision_id
        else:
            url = base + "/" + decision_id
        client = await get_http_client()
        r = await client.get(url)
        r.raise_for_status()
        return dict(r.json())

    # ------------------------ Cycle ----------------------------------------
    async def route_event(
        self,
        event: dict[str, Any],
        affect_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Single-event cognitive cycle.
        Body shape: {"event": {...}, "affect_override": {...}}
        """
        payload: dict[str, Any] = {"event": event}
        if affect_override is not None:
            payload["affect_override"] = affect_override
        client = await get_http_client()
        r = await client.post(ENDPOINTS.ATUNE_ROUTE, json=payload)
        r.raise_for_status()
        return dict(r.json())

    async def cognitive_cycle(
        self,
        events: list[dict[str, Any]],
        affect_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Batch cognitive cycle.
        Body shape: {"events":[...], "affect_override": {...}}
        """
        payload: dict[str, Any] = {"events": events}
        if affect_override is not None:
            payload["affect_override"] = affect_override
        client = await get_http_client()
        r = await client.post(ENDPOINTS.ATUNE_COGNITIVE_CYCLE, json=payload)
        r.raise_for_status()
        return dict(r.json())

    # ------------------------ Unity bridge ----------------------------------
    async def escalate_unity(
        self,
        payload: dict[str, Any],
        *,
        budget_ms: int | None = None,
    ) -> dict[str, Any]:
        """
        Atune-owned bridge to Unity deliberation.
        Pass x-budget-ms if you want Atune to forward a budget header to Unity.
        """
        headers: dict[str, str] = {}
        if budget_ms is not None:
            headers["x-budget-ms"] = str(int(budget_ms))
        client = await get_http_client()
        r = await client.post(ENDPOINTS.ATUNE_ESCALATE, json=payload, headers=headers)
        r.raise_for_status()
        return dict(r.json())

    # ------------------------ Market (scorecard → event) --------------------
    async def publish_bid(
        self,
        scorecard: dict[str, Any],
        affect_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Canonical ingress: publish a scorecard as an AxonEvent to /atune/route.
        Event type: "evo.scorecard". No bespoke /market/bids endpoint.
        """
        eid = f"bid_{_hash16(scorecard)}"
        event = {
            "event_id": eid,
            "t_observed": 0,
            "source": "evo",
            "event_type": "evo.scorecard",
            "modality": "json",
            "parsed": {"json": scorecard},
            "embeddings": {},
            "provenance": {"component": "evo", "kind": "scorecard"},
            "salience_hints": {},
            "quality": {},
            "triangulation": {},
            "cost_ms": 0,
            "cost_usd": 0.0,
        }
        return await self.route_event(event, affect_override=affect_override)
