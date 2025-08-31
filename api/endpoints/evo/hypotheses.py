# file: api/endpoints/evo/hypotheses.py
from __future__ import annotations

import time

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel

from systems.evo.runtime import get_engine
from systems.evo.schemas import ConflictID, Hypothesis

hypotheses_router = APIRouter(tags=["evo-hypotheses"])
_engine = get_engine()


def _stamp_cost(res: Response, start: float) -> None:
    ms = int((time.perf_counter() - start) * 1000)
    res.headers["X-Cost-MS"] = str(ms)


class SpawnRequest(BaseModel):
    conflict_ids: list[ConflictID]
    strategies: list[str] | None = None
    budget_ms: int | None = None


@hypotheses_router.post("/spawn", response_model=list[Hypothesis])
def spawn_hypotheses(
    req: SpawnRequest,
    response: Response,
    x_budget_ms: int | None = Header(default=None),
) -> list[Hypothesis]:
    t0 = time.perf_counter()
    budget = req.budget_ms if req.budget_ms is not None else (x_budget_ms or None)
    out = _engine.hypotheses.spawn(req.conflict_ids, strategies=req.strategies, budget_ms=budget)
    _stamp_cost(response, t0)
    return out
