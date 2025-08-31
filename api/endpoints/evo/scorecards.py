# file: api/endpoints/evo/scorecards.py
from __future__ import annotations

import json
import time
from hashlib import blake2s

from fastapi import APIRouter, Response
from pydantic import BaseModel

from systems.evo.scorecards.exporter import ScorecardExporter

scorecards_router = APIRouter(tags=["evo-scorecards"])
_exporter = ScorecardExporter()


def _stamp_cost(res: Response, start: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - start) * 1000))


def _hash(d: dict) -> str:
    return blake2s(json.dumps(d, sort_keys=True).encode("utf-8")).hexdigest()[:16]


class ExportRequest(BaseModel):
    escalation_result: dict


@scorecards_router.post("/export", response_model=dict)
def export_scorecard(req: ExportRequest, response: Response) -> dict:
    t0 = time.perf_counter()
    card = _exporter.build(req.escalation_result)
    response.headers["X-Scorecard-Hash"] = _hash(card)
    _stamp_cost(response, t0)
    return card
