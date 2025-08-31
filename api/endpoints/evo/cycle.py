from __future__ import annotations

import time

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel

from systems.evo.runtime import get_engine
from systems.evo.schemas import ConflictID

cycle_router = APIRouter(tags=["evo-cycle"])
_engine = get_engine()


def _stamp_cost(res: Response, start: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - start) * 1000))


class CycleRequest(BaseModel):
    conflict_ids: list[ConflictID]
    arm: str | None = None
    budget_ms: int | None = None


@cycle_router.post("/cycle", response_model=dict)
async def run_cycle(
    req: CycleRequest,
    response: Response,
    x_budget_ms: int | None = Header(default=None),
    x_arm: str | None = Header(default=None),
) -> dict:
    """
    Drive a full EVO metabolic cycle:
      - Obviousness → branch
      - local_fix: evidence → proposal → Equor attest → Atune route
      - escalate: Atune advisory + Nova propose/evaluate/auction
    """
    t0 = time.perf_counter()
    arm = req.arm or x_arm
    budget = req.budget_ms if req.budget_ms is not None else (x_budget_ms or None)
    out = await _engine.run_cycle(req.conflict_ids, externally_selected_arm=arm, budget_ms=budget)
    _stamp_cost(response, t0)
    return out
