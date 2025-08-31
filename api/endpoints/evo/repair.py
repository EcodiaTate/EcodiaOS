# file: api/endpoints/evo/repair.py
from __future__ import annotations

import time

from fastapi import APIRouter, Path, Query, Response
from pydantic import BaseModel

from systems.evo.repair.tracker import RepairTicket, RepairTracker

repair_router = APIRouter(tags=["evo-repair"])
_tracker = RepairTracker()


def _stamp_cost(res: Response, t0: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - t0) * 1000))


class RecordRequest(BaseModel):
    proposal_id: str
    simula_ticket_id: str
    provenance: dict = {}


@repair_router.post("/record", response_model=RepairTicket)
def record(req: RecordRequest, response: Response) -> RepairTicket:
    t0 = time.perf_counter()
    ticket = _tracker.record(req.proposal_id, req.simula_ticket_id, req.provenance)
    _stamp_cost(response, t0)
    return ticket


class UpdateRequest(BaseModel):
    status: str
    notes: str | None = None


@repair_router.post("/update/{ticket_id}", response_model=RepairTicket)
def update(
    ticket_id: str = Path(...),
    req: UpdateRequest = None,
    response: Response = None,
) -> RepairTicket:
    t0 = time.perf_counter()
    ticket = _tracker.update(ticket_id, req.status, req.notes if req else None)
    if response is not None:
        _stamp_cost(response, t0)
    return ticket


@repair_router.get("/ticket/{ticket_id}", response_model=RepairTicket)
def get_ticket(ticket_id: str = Path(...), response: Response = None) -> RepairTicket:
    t0 = time.perf_counter()
    t = _tracker.get(ticket_id)
    if response is not None:
        _stamp_cost(response, t0)
    return t


@repair_router.get("/list", response_model=list[RepairTicket])
def list_tickets(
    proposal_id: str | None = Query(default=None),
    response: Response = None,
) -> list[RepairTicket]:
    t0 = time.perf_counter()
    out = _tracker.list(proposal_id=proposal_id)
    if response is not None:
        _stamp_cost(response, t0)
    return out
