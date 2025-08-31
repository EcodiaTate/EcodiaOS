from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel

from systems.nova.hyper.hyperengine import NovaHyperEngine
from systems.nova.schemas import InnovationBrief, InventionCandidate

router = APIRouter(prefix="/hyper", tags=["nova-hyper"])
_engine = NovaHyperEngine()


def _stamp_cost(res: Response, t0: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - t0) * 1000))


class HyperRunResult(BaseModel):
    decision_id: str
    capsule_id: str
    winners: list[str]
    portfolio: list[str]
    auction: dict[str, Any] = {}


@router.post("/propose", response_model=list[InventionCandidate])
async def hyper_propose(
    brief: InnovationBrief,
    response: Response,
    x_budget_ms: int | None = Header(None),
    x_decision_id: str | None = Header(None),
) -> list[InventionCandidate]:
    t0 = time.perf_counter()
    cands = await _engine.propose(
        brief,
        budget_ms=int(x_budget_ms or 5000),
        decision_id=(x_decision_id or ""),
    )
    if x_decision_id:
        response.headers["X-Decision-Id"] = x_decision_id
    _stamp_cost(response, t0)
    return cands


@router.post("/run", response_model=HyperRunResult)
async def hyper_run(
    brief: InnovationBrief,
    response: Response,
    x_budget_ms: int | None = Header(None),
    x_decision_id: str | None = Header(None),
) -> HyperRunResult:
    t0 = time.perf_counter()
    res = await _engine.run_end_to_end(
        brief,
        budget_ms=int(x_budget_ms or 8000),
        decision_id=x_decision_id,
    )
    if x_decision_id:
        response.headers["X-Decision-Id"] = x_decision_id
    _stamp_cost(response, t0)
    return HyperRunResult(**res)
