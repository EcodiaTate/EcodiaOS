# api/endpoints/evo/conflicts.py
# DESCRIPTION: Aligned with the modern ConflictsService.batch() method for
# improved robustness and performance.

from __future__ import annotations

import time
from typing import Any, List

from fastapi import APIRouter, Path, Query, Response, HTTPException
from pydantic import BaseModel

from systems.evo.runtime import get_engine
from systems.evo.schemas import ConflictID, ConflictNode

conflicts_router = APIRouter(tags=["evo-conflicts"])
_engine = get_engine()

def _stamp_cost(res: Response, start: float) -> None:
    ms = int((time.perf_counter() - start) * 1000)
    res.headers["X-Cost-MS"] = str(ms)


class BatchRequest(BaseModel):
    conflicts: List[ConflictNode | dict]

@conflicts_router.post("/batch", response_model=dict)
def create_conflicts_batch(req: BatchRequest, response: Response) -> dict:
    """
    Intakes a batch of conflicts using the canonical, deduplicating service method.
    """
    t0 = time.perf_counter()
    # USE THE MODERN BATCH METHOD: This leverages the robust, deduplicating,
    # and background-persisting logic of the canonical ConflictsService.
    result = _engine.intake_conflicts(req.conflicts)
    _stamp_cost(response, t0)
    return result


@conflicts_router.get("/open", response_model=list[ConflictNode])
def list_open_conflicts(
    response: Response,
    limit: int | None = Query(default=None, ge=1),
) -> list[ConflictNode]:
    t0 = time.perf_counter()
    out = _engine.conflicts.list_open(limit=limit)
    _stamp_cost(response, t0)
    return out


@conflicts_router.get("/{conflict_id}", response_model=ConflictNode)
def get_conflict(conflict_id: ConflictID = Path(...), response: Response = None) -> ConflictNode:
    t0 = time.perf_counter()
    # Use the safe 'peek' method to avoid potential KeyErrors in the API layer.
    out = _engine.conflicts.peek(conflict_id)
    if out is None:
        raise HTTPException(status_code=404, detail=f"Conflict ID '{conflict_id}' not found.")
    if response is not None:
        _stamp_cost(response, t0)
    return out