# api/endpoints/metrics/atune_metrics.py
from __future__ import annotations

from fastapi import APIRouter

from core.metrics.registry import REGISTRY

router = APIRouter()


@router.get("/__metrics__/atune")
async def atune_metrics():
    return {
        "counters": {k: v.value for k, v in REGISTRY.counters.items() if k.startswith("atune.")},
        "gauges": {k: v.value for k, v in REGISTRY.gauges.items() if k.startswith("atune.")},
    }
