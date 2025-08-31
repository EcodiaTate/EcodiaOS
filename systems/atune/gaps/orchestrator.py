# systems/atune/gaps/orchestrator.py
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.atune.gaps.schema import CapabilityGapEvent


async def submit_capability_gap(
    gap: CapabilityGapEvent,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Posts a CapabilityGapEvent to Axon's Probecraft intake.
    Preserves budget headers (x-budget-ms, x-deadline-ts, x-decision-id) if provided.
    """
    client = await get_http_client()
    path = getattr(ENDPOINTS, "AXON_PROBECRAFT_INTAKE", "/probecraft/intake")
    try:
        r = await client.post(path, json=gap.model_dump(), headers=headers or {})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"probecraft_intake_failed: {e}")
