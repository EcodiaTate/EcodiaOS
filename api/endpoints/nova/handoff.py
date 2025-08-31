# file: api/endpoints/nova/handoff.py
from __future__ import annotations

import time

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel

from systems.nova.runners.patch_handoff import PatchHandoff
from systems.nova.schemas import InnovationBrief, InventionCandidate
from systems.nova.types.patch import SimulaPatchBrief, SimulaPatchTicket

router = APIRouter(prefix="/handoff", tags=["nova-handoff"])
_ph = PatchHandoff()


def _stamp_cost(res: Response, t0: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - t0) * 1000))


class HandoffRequest(BaseModel):
    brief: InnovationBrief
    winner: InventionCandidate


@router.post("/patch/prepare", response_model=SimulaPatchBrief)
async def prepare_patch(
    req: HandoffRequest,
    response: Response,
    x_decision_id: str | None = Header(None),
) -> SimulaPatchBrief:
    t0 = time.perf_counter()
    sb = _ph.to_brief(req.brief, req.winner, decision_id=x_decision_id)

    # Telemetry/correlation headers
    if x_decision_id:
        response.headers["X-Decision-Id"] = x_decision_id
    # Expose which candidate we’re preparing a patch for
    try:
        response.headers["X-Nova-Winner-Candidate"] = str(
            getattr(req.winner, "candidate_id", "") or "",
        )
    except Exception:
        pass

    _stamp_cost(response, t0)
    return sb


@router.post("/patch/submit", response_model=SimulaPatchTicket)
async def submit_patch(
    sb: SimulaPatchBrief,
    response: Response,
    x_decision_id: str | None = Header(None),
) -> SimulaPatchTicket:
    t0 = time.perf_counter()
    ticket = await _ph.submit(sb, decision_id=x_decision_id)

    # Telemetry/correlation headers
    if x_decision_id:
        response.headers["X-Decision-Id"] = x_decision_id
    # Surface ticket id for easy harvesting downstream
    try:
        response.headers["X-Simula-Ticket-Id"] = str(getattr(ticket, "ticket_id", "") or "")
    except Exception:
        pass

    _stamp_cost(response, t0)
    return ticket
