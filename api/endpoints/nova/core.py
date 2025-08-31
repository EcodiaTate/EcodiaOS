from __future__ import annotations

import json
import time
from hashlib import blake2s
from typing import Any

from fastapi import APIRouter, Header, Path, Response
from pydantic import BaseModel  # REFACTORED: Import BaseModel

from systems.nova.clients.synapse_client import SynapseBudgetClient
from systems.nova.hyper.hyperengine import NovaHyperEngine
from systems.nova.ledger.ledger import NovaLedger
from systems.nova.playbooks.registry import PLAYBOOK_REGISTRY
from systems.nova.proof.pcc import ProofResult, ProofVM
from systems.nova.proof.pcc_ext import ProofVMExt
from systems.nova.runners.auction_client import AuctionClient
from systems.nova.runners.eval_runner import EvalRunner
from systems.nova.runners.playbook_runner import PlaybookRunner
from systems.nova.runners.portfolio_runner import PortfolioRunner
from systems.nova.runners.rollout_client import RolloutClient
from systems.nova.schemas import (
    AuctionResult,
    DesignCapsule,
    InnovationBrief,
    InventionCandidate,
    RolloutRequest,
    RolloutResult,
)
from systems.nova.telemetry.hooks import (
    headers_for_auction,
    headers_for_evaluate,
    headers_for_propose,
)

# REFACTORED: Define Pydantic models for request bodies
# ----------------------------------------------------
class CandidateListRequest(BaseModel):
    """Request body for endpoints that accept a list of InventionCandidates."""
    candidates: list[InventionCandidate]

class SaveCapsuleRequest(BaseModel):
    """Request body for the save_capsule endpoint."""
    brief: InnovationBrief
    artifacts: list[Any] = []
    playbook_dag: dict | None = None
    eval_logs: dict | None = None
    counterfactuals: list[Any] | None = None
    costs: dict | None = None
    env_pins: dict | None = None
    seeds: dict | None = None

class ProofCheckRequest(BaseModel):
    """Request body for the proof_check endpoint."""
    capability_spec: dict = {}
    obligations: dict = {}
    evidence: dict | None = None

class ProofCheckExtRequest(ProofCheckRequest):
    """Request body for the proof_check_ext endpoint, extending the base proof check."""
    brief_success: dict | None = None
# ----------------------------------------------------

router = APIRouter()
_ledger = NovaLedger()
_playbooks = PlaybookRunner()
_eval = EvalRunner()
_auction = AuctionClient()
_rollout = RolloutClient()
_pvm = ProofVM()
_syn_budget = SynapseBudgetClient()
_hyper = NovaHyperEngine()

_portfolio = PortfolioRunner()
_pvm_ext = ProofVMExt()


def _stamp_cost(res: Response, start: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - start) * 1000))


def _hash(obj: object) -> str:
    return blake2s(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


@router.post("/propose", response_model=list[InventionCandidate])
async def propose(
    brief: InnovationBrief,
    response: Response,
    x_budget_ms: int | None = Header(None),
    x_deadline_ts: int | None = Header(None),
    x_decision_id: str | None = Header(None),
) -> list[InventionCandidate]:
    t0 = time.perf_counter()
    budget_ms = int(x_budget_ms or 0)
    if budget_ms == 0:
        budget_ms = await _syn_budget.allocate_budget_ms(brief.dict())

    cands = await _hyper.propose(brief, budget_ms=budget_ms, decision_id=(x_decision_id or ""))
    response.headers.update(
        headers_for_propose([c.dict() if hasattr(c, "dict") else c for c in cands]),
    )
    if x_decision_id:
        response.headers["X-Decision-Id"] = x_decision_id
    _stamp_cost(response, t0)
    return cands


@router.post("/evaluate", response_model=list[InventionCandidate])
async def evaluate(
    # REFACTORED: Use Pydantic model for request body validation
    request: CandidateListRequest,
    response: Response,
) -> list[InventionCandidate]:
    t0 = time.perf_counter()
    # REFACTORED: Access candidates via the request model
    out = await _eval.run_tests(request.candidates)
    response.headers.update(
        headers_for_evaluate([c.dict() if hasattr(c, "dict") else c for c in out]),
    )
    _stamp_cost(response, t0)
    return out


@router.post("/auction", response_model=AuctionResult)
async def auction(
    # REFACTORED: Use Pydantic model for request body validation
    request: CandidateListRequest,
    response: Response,
    x_budget_ms: int | None = Header(None),
    x_decision_id: str | None = Header(None),
) -> AuctionResult:
    t0 = time.perf_counter()
    # REFACTORED: Access candidates via the request model
    res = await _auction.auction(request.candidates, budget_ms=int(x_budget_ms or 0))
    response.headers.update(headers_for_auction(res if isinstance(res, dict) else res.dict()))
    if x_decision_id:
        response.headers["X-Decision-Id"] = x_decision_id
    response.headers["X-Market-Receipt-Hash"] = res.market_receipt.get("hash", "")
    _stamp_cost(response, t0)
    return res


@router.post("/capsule/save", response_model=DesignCapsule)
async def save_capsule(
    # REFACTORED: Use Pydantic model for request body validation
    request: SaveCapsuleRequest,
    response: Response,
) -> DesignCapsule:
    t0 = time.perf_counter()
    # REFACTORED: Use validated data from the request model directly
    dc = await _ledger.save_capsule(
        brief=request.brief,
        artifacts=request.artifacts,
        playbook_dag=request.playbook_dag,
        eval_logs=request.eval_logs,
        counterfactuals=request.counterfactuals,
        costs=request.costs,
        env_pins=request.env_pins,
        seeds=request.seeds,
    )
    response.headers["X-DesignCapsule-Hash"] = _hash(dc.dict())
    _stamp_cost(response, t0)
    return dc


@router.post("/proof/check", response_model=ProofResult)
async def proof_check(
    # REFACTORED: Use Pydantic model for request body validation
    request: ProofCheckRequest,
    response: Response
) -> ProofResult:
    t0 = time.perf_counter()
    # REFACTORED: Use validated data from the request model
    res = _pvm.check(
        capability_spec=request.capability_spec,
        obligations=request.obligations,
        evidence=request.evidence,
    )
    _stamp_cost(response, t0)
    return res


@router.post("/proof/check_ext", response_model=ProofResult, tags=["nova-proof"])
async def proof_check_ext(
    # REFACTORED: Use Pydantic model for request body validation
    request: ProofCheckExtRequest,
    response: Response
) -> ProofResult:
    t0 = time.perf_counter()
    # REFACTORED: Use validated data from the request model
    res = _pvm_ext.check(
        capability_spec=request.capability_spec,
        obligations=request.obligations,
        evidence=request.evidence,
        brief_success=request.brief_success,
    )
    _stamp_cost(response, t0)
    return res


@router.post("/rollout", response_model=RolloutResult)
async def rollout(req: RolloutRequest, response: Response) -> RolloutResult:
    t0 = time.perf_counter()
    res = await _rollout.rollout(req)
    _stamp_cost(response, t0)
    return res


@router.get("/archive/{capsule_id}", response_model=DesignCapsule)
async def get_capsule(capsule_id: str = Path(...)) -> DesignCapsule:
    return await _ledger.get_capsule(capsule_id)


@router.get("/playbooks", response_model=list[dict])
async def list_playbooks() -> list[dict]:
    return [{"name": "map_elites.search"}, {"name": "dreamcoder.library"}, {"name": "tot.mcts"}]


@router.get("/playbooks/registry", response_model=list[dict], tags=["nova-playbooks"])
async def list_playbooks_registry() -> list[dict]:
    try:
        names = [cls.name for cls in PLAYBOOK_REGISTRY]
    except Exception:
        names = []
    if "meta.compose" not in names:
        names.append("meta.compose")
    return [{"name": n} for n in sorted(names)]