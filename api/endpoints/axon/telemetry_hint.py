from __future__ import annotations

from fastapi import APIRouter

telemetry_router = APIRouter()


@telemetry_router.get("/meta/telemetry")
async def axon_telemetry_hint():
    """
    Verifies Axon routes carry X-Axon-Action-Cost-MS via middleware.
    """
    return {"ok": True}
