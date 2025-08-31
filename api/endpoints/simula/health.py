from __future__ import annotations

import time

from fastapi import APIRouter

sim_health_router = APIRouter()


@sim_health_router.get("/sim_health")
async def health():
    # Keep health cheap for Docker healthcheck frequency
    return {
        "status": "ok",
        "ts": int(time.time()),
        "service": "simula",
        "version": "0.1.0",
    }
