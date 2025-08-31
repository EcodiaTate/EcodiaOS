# file: api/endpoints/evo/replay.py
from __future__ import annotations

import time

from fastapi import APIRouter, Path, Response

from systems.evo.runtime import get_engine
from systems.evo.schemas import ReplayCapsuleID

replay_router = APIRouter(tags=["evo-replay"])
_engine = get_engine()


def _stamp_cost(res: Response, start: float) -> None:
    ms = int((time.perf_counter() - start) * 1000)
    res.headers["X-Cost-MS"] = str(ms)


@replay_router.get("/{capsule_id}/manifest", response_model=dict)
def get_replay_manifest(capsule_id: ReplayCapsuleID = Path(...), response: Response = None) -> dict:
    t0 = time.perf_counter()
    out = _engine.replay.manifest(capsule_id)
    if response is not None:
        _stamp_cost(response, t0)
    return out


@replay_router.post("/{capsule_id}/verify", response_model=dict)
def verify_replay_capsule(
    capsule_id: ReplayCapsuleID = Path(...),
    response: Response = None,
) -> dict:
    t0 = time.perf_counter()
    ok = _engine.replay.verify(capsule_id)
    if response is not None:
        _stamp_cost(response, t0)
    return {"ok": ok}
