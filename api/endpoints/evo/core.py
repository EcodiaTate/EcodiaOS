# file: api/endpoints/evo/core.py
from __future__ import annotations

import time

from fastapi import APIRouter, Response

core_router = APIRouter(tags=["evo-core"])


def _stamp_cost(res: Response, start: float) -> None:
    ms = int((time.perf_counter() - start) * 1000)
    res.headers["X-Cost-MS"] = str(ms)


@core_router.get("/ping")
def ping(response: Response) -> dict:
    t0 = time.perf_counter()
    out = {"ok": True, "service": "evo"}
    _stamp_cost(response, t0)
    return out
