# file: api/endpoints/nova/winner.py
from __future__ import annotations

import time

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel

from systems.nova.pipelines.winner_pipeline import WinnerPipeline
from systems.nova.schemas import AuctionResult, InnovationBrief, InventionCandidate
from systems.nova.types.patch import SimulaPatchBrief

router = APIRouter(tags=["nova-winner"])
_pipe = WinnerPipeline()


def _stamp_cost(res: Response, t0: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - t0) * 1000))


class SubmitRequest(BaseModel):
    brief: InnovationBrief
    candidates: list[InventionCandidate]
    auction: AuctionResult
    env_pins: dict = {}
    seeds: dict = {}


@router.post("/winner/prepare", response_model=SimulaPatchBrief)
async def prepare_winner_patch(
    req: SubmitRequest,
    response: Response,
    x_decision_id: str | None = Header(None),
) -> SimulaPatchBrief:
    t0 = time.perf_counter()
    # Select the top winner and return a preview patch brief (no submission)
    winners = {w for w in (req.auction.winners or [])}
    pick = next((c for c in req.candidates if c.candidate_id in winners), None)

    # Telemetry/correlation headers
    response.headers["X-Nova-Winners"] = str(len(winners))
    if pick is not None:
        response.headers["X-Nova-Winner-Candidate"] = str(pick.candidate_id)

    if pick is None:
        # Preserve original fallback shape
        res = SimulaPatchBrief(
            brief_id="sb_invalid",
            candidate_id="none",
            playbook="none",
            problem=req.brief.problem,
            context=req.brief.context or {},
        )
        _stamp_cost(response, t0)
        return res

    pb = _pipe._build_patch_brief(req.brief, pick, x_decision_id)
    if x_decision_id:
        response.headers["X-Decision-Id"] = x_decision_id
    _stamp_cost(response, t0)
    return pb


@router.post("/winner/submit", response_model=dict)
async def submit_winner(
    req: SubmitRequest,
    response: Response,
    x_decision_id: str | None = Header(None),
) -> dict:
    t0 = time.perf_counter()
    out = await _pipe.run(
        brief=req.brief,
        candidates=req.candidates,
        auction=req.auction,
        decision_id=x_decision_id,
        env_pins=req.env_pins,
        seeds=req.seeds,
    )

    # Telemetry/correlation headers
    if x_decision_id:
        response.headers["X-Decision-Id"] = x_decision_id
    try:
        # These keys are produced by WinnerPipeline.run(...)
        # {"ok": True, "decision_id": ..., "winner_id": ..., "simula_ticket": {...}, "design_capsule_id": "..."}
        if "winner_id" in out:
            response.headers["X-Nova-Winner-Candidate"] = str(out.get("winner_id", ""))
        sim_ticket = (
            (out.get("simula_ticket") or {}).get("ticket_id")
            if isinstance(out.get("simula_ticket"), dict)
            else None
        )
        if sim_ticket:
            response.headers["X-Simula-Ticket-Id"] = str(sim_ticket)
        if "design_capsule_id" in out:
            response.headers["X-DesignCapsule-Id"] = str(out.get("design_capsule_id", ""))
    except Exception:
        pass

    _stamp_cost(response, t0)
    return out
