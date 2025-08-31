# api/endpoints/atune/meta_endpoints.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

meta_router = APIRouter()

# Keep in sync with actual mounts in api/endpoints/atune/__init__.py
_ATUNE_ENDPOINT_MAP = {
    "POST /atune/route": "Single event → cognitive cycle",
    "POST /atune/cognitive_cycle": "Batch plan/act",
    "POST /atune/escalate": "Unity handoff",
    "GET  /atune/meta/status": "Budget/focus/env/secl",
    "GET  /atune/meta/endpoints": "This list",
}


@meta_router.get("/meta/endpoints")
async def atune_meta_endpoints() -> dict[str, Any]:
    return {"map": _ATUNE_ENDPOINT_MAP}
