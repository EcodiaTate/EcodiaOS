from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

cache_hygiene_router = APIRouter()

try:
    from systems.simula.code_sim.cache.patch_cache import get as cache_get  # type: ignore
    from systems.simula.code_sim.cache.patch_cache import put as cache_put
except Exception:  # pragma: no cover
    cache_get = cache_put = None


class CacheGetReq(BaseModel):
    diff: str


class CachePutReq(BaseModel):
    diff: str
    static_ok: bool
    tests_ok: bool
    delta_cov_pct: float = 0.0
    payload: dict[str, Any] = Field(default_factory=dict)


@cache_hygiene_router.post("/get")
async def hygiene_get(req: CacheGetReq) -> dict[str, Any]:
    if not cache_get:
        raise HTTPException(status_code=501, detail="cache not available")
    c = cache_get(req.diff)
    return {"ok": bool(c), "cache": (c.__dict__ if c else None)}


@cache_hygiene_router.post("/put")
async def hygiene_put(req: CachePutReq) -> dict[str, Any]:
    if not cache_put:
        raise HTTPException(status_code=501, detail="cache not available")
    cache_put(req.diff, req.static_ok, req.tests_ok, req.delta_cov_pct, req.payload)
    return {"ok": True}
