# systems/axon/events/emitter.py
from __future__ import annotations

import asyncio
import os
from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client

ENDPOINT_ATTRS = ("ATUNE_ROUTE", "ATUNE_COGNITIVE_CYCLE")
_DEBUG = os.getenv("AXON_DEBUG", "0") == "1"


async def emit_followups(events: list[dict[str, Any]], decision_id: str | None = None) -> None:
    if not events:
        return
    client = await get_http_client()

    # choose best-known endpoint name dynamically
    target = None
    for name in ENDPOINT_ATTRS:
        if hasattr(ENDPOINTS, name):
            target = getattr(ENDPOINTS, name)
            break
    target = target or "/atune/route"

    headers = {"x-budget-ms": os.getenv("AXON_EMIT_BUDGET_MS", "800")}
    if decision_id:
        headers["x-decision-id"] = decision_id

    try:
        if len(events) == 1 and hasattr(ENDPOINTS, "ATUNE_ROUTE"):
            resp = await client.post(getattr(ENDPOINTS, "ATUNE_ROUTE"), json=events[0], headers=headers)
            if _DEBUG:
                print(f"[Emitter] POST {getattr(ENDPOINTS, 'ATUNE_ROUTE')} → {resp.status_code}")
        else:
            if hasattr(ENDPOINTS, "ATUNE_COGNITIVE_CYCLE"):
                resp = await client.post(getattr(ENDPOINTS, "ATUNE_COGNITIVE_CYCLE"), json={ "events": events }, headers=headers)
                if _DEBUG:
                    print(f"[Emitter] POST {getattr(ENDPOINTS, 'ATUNE_COGNITIVE_CYCLE')} → {resp.status_code}")
            else:
                for ev in events:
                    resp = await client.post(target, json=ev, headers=headers)
                    if _DEBUG:
                        print(f"[Emitter] POST {target} → {resp.status_code}")
    except Exception as e:
        if _DEBUG:
            print(f"[Emitter] swallow error: {e}")
        return


def emit_followups_bg(events: list[dict[str, Any]], decision_id: str | None = None) -> None:
    try:
        asyncio.create_task(emit_followups(events, decision_id=decision_id))
    except Exception:
        pass
