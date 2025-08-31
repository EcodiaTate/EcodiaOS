# file: api/endpoints/evo/evidence.py
from __future__ import annotations

import time

from fastapi import APIRouter, Path, Response
from pydantic import BaseModel

from systems.evo.runtime import get_engine
from systems.evo.schemas import EvidenceBundle, Hypothesis, ReplayCapsuleID, TicketID

# Fallback orchestrator if engine doesn't expose one (keeps API resilient)
try:
    from systems.evo.evidence.collector import EvidenceOrchestrator  # type: ignore
except Exception:  # pragma: no cover
    EvidenceOrchestrator = None  # type: ignore

evidence_router = APIRouter(tags=["evo-evidence"])
_engine = get_engine()
_eo = getattr(_engine, "evidence", EvidenceOrchestrator() if EvidenceOrchestrator else None)


def _stamp_cost(res: Response, start: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - start) * 1000))


class PlanResponse(BaseModel):
    plan: dict


class RequestResponse(BaseModel):
    ticket_id: TicketID


class AttachReplayRequest(BaseModel):
    evidence: EvidenceBundle


class AttachReplayResponse(BaseModel):
    replay_capsule_id: ReplayCapsuleID


@evidence_router.post("/plan", response_model=PlanResponse)
def plan_suite(hypothesis: Hypothesis, response: Response) -> PlanResponse:
    t0 = time.perf_counter()
    plan = _eo.plan_suite(hypothesis) if _eo else {}
    _stamp_cost(response, t0)
    return PlanResponse(plan=plan)


@evidence_router.post("/request", response_model=RequestResponse)
def request_collection(hypothesis: Hypothesis, response: Response) -> RequestResponse:
    t0 = time.perf_counter()
    ticket = _eo.request(hypothesis) if _eo else TicketID("tkt_missing")
    _stamp_cost(response, t0)
    return RequestResponse(ticket_id=ticket)


@evidence_router.get("/collect/{ticket_id}", response_model=EvidenceBundle)
def collect(ticket_id: TicketID = Path(...), response: Response = None) -> EvidenceBundle:
    t0 = time.perf_counter()
    bundle = (
        _eo.collect(ticket_id)
        if _eo
        else EvidenceBundle(evidence_id="ev_missing", hypothesis_id="unknown")
    )
    if response is not None:
        _stamp_cost(response, t0)
    return bundle


@evidence_router.post("/attach-replay", response_model=AttachReplayResponse)
def attach_replay(req: AttachReplayRequest, response: Response) -> AttachReplayResponse:
    t0 = time.perf_counter()
    rcid = _eo.attach_replay_capsule(req.evidence) if _eo else ReplayCapsuleID("rc_missing")
    _stamp_cost(response, t0)
    return AttachReplayResponse(replay_capsule_id=rcid)
