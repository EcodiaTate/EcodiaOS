from __future__ import annotations

import time

from fastapi import APIRouter, Response
from pydantic import BaseModel

from systems.evo.runtime import get_engine
from systems.evo.schemas import ConflictNode, ObviousnessReport

# Fallback gate if engine doesn't expose one
try:
    from systems.evo.gates.obviousness import ObviousnessGate  # type: ignore
except Exception:  # pragma: no cover
    ObviousnessGate = None  # type: ignore

obviousness_router = APIRouter(tags=["evo-obviousness"])
_engine = get_engine()
_gate = getattr(_engine, "obviousness", ObviousnessGate() if ObviousnessGate else None)


def _stamp_cost(res: Response, start: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - start) * 1000))


class ScoreRequest(BaseModel):
    conflicts: list[ConflictNode]


@obviousness_router.post("/score", response_model=ObviousnessReport)
def score_obviousness(req: ScoreRequest, response: Response) -> ObviousnessReport:
    t0 = time.perf_counter()
    rep = (
        _gate.score(req.conflicts)
        if _gate
        else ObviousnessReport(
            conflict_ids=[],
            is_obvious=False,
            score=0.0,
            confidence=0.0,
            model_version="fallback",
        )
    )
    _stamp_cost(response, t0)
    return rep
