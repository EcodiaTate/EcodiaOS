# api/endpoints/atune/meta_status.py
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from api.endpoints.atune import route_event as RE
from systems.atune.metrics.secl_counters import snapshot as secl_snapshot

meta_status_router = APIRouter()


def _env_flag(k: str, default: str = "0") -> str:
    return os.getenv(k, default)


@meta_status_router.get("/meta/status")
async def atune_meta_status() -> dict[str, Any]:
    try:
        pool = getattr(RE.budget_manager, "pool_ms_per_tick", None)
        avail = RE.budget_manager.get_available_budget() if hasattr(RE, "budget_manager") else None
        gamma = getattr(RE.tuner, "leak_gamma", None)
    except Exception:
        pool, avail, gamma = None, None, None

    env_flags = {
        "ATUNE_AB_ENABLED": _env_flag("ATUNE_AB_ENABLED", "1"),
        "ATUNE_MARKET_STRATEGY": _env_flag("ATUNE_MARKET_STRATEGY", "vcg"),
        "AXON_ROLLBACK_ENABLED": _env_flag("AXON_ROLLBACK_ENABLED", "1"),
        "AXON_ESCALATE_ON_POSTCOND": _env_flag("AXON_ESCALATE_ON_POSTCOND", "1"),
        "AXON_MIRROR_SHADOW_PCT": _env_flag("AXON_MIRROR_SHADOW_PCT", "0.10"),
    }

    return {
        "now_utc": datetime.now(UTC).isoformat(),
        "budget": {"pool_ms_per_tick": pool, "available_ms_now": avail},
        "focus": {"leak_gamma": gamma},
        "env_flags": env_flags,
        "secl": secl_snapshot(),
    }
