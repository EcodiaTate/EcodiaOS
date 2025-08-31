# file: api/endpoints/evo/proposals.py
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Path, Response
from pydantic import BaseModel

from systems.evo.runtime import get_engine
from systems.evo.schemas import EvidenceBundle, Hypothesis, Proposal, ProposalID

proposals_router = APIRouter(tags=["evo-proposals"])
_engine = get_engine()


def _stamp_cost(res: Response, start: float) -> None:
    ms = int((time.perf_counter() - start) * 1000)
    res.headers["X-Cost-MS"] = str(ms)


class AssembleRequest(BaseModel):
    title: str
    summary: str
    hypotheses: list[Hypothesis]
    evidence: list[EvidenceBundle]


@proposals_router.post("/assemble", response_model=Proposal)
def assemble_proposal(req: AssembleRequest, response: Response) -> Proposal:
    t0 = time.perf_counter()
    p = _engine.assembler.assemble(req.hypotheses, req.evidence, req.title, req.summary)
    _engine.assembler.validate_completeness(p)
    _stamp_cost(response, t0)
    return p


@proposals_router.get("/{proposal_id}", response_model=Proposal)
def get_proposal(proposal_id: ProposalID = Path(...), response: Response = None) -> Proposal:
    t0 = time.perf_counter()
    try:
        p = _engine.assembler.get(proposal_id)  # expected API; raise if absent
    except AttributeError:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
    if p is None:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
    if response is not None:
        _stamp_cost(response, t0)
    return p


@proposals_router.post("/{proposal_id}/handover", response_model=dict)
def handover_proposal(proposal_id: ProposalID = Path(...), response: Response = None) -> dict:
    t0 = time.perf_counter()
    out = (
        _engine.assembler.handover(proposal_id)
        if hasattr(_engine.assembler, "handover")
        else {"handover_ref": f"handover:{proposal_id}"}
    )
    if response is not None:
        _stamp_cost(response, t0)
    return out
