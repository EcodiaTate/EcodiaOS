# systems/evo/engine.py
# DESCRIPTION: Major refactor to align with EOS Bible's Separation of Concerns.
# Uses dedicated clients and routers instead of direct HTTP calls.

from __future__ import annotations
import uuid
import traceback
from typing import Any

from systems.evo.clients.nova_client import NovaClient
from systems.evo.conflicts.store import ConflictsService
from systems.evo.gates.obviousness import ObviousnessGate
from systems.evo.hypotheses.factory import HypothesisService
from systems.evo.journal.ledger import EvoLedger
from systems.evo.proposals import ProposalAssembler
from systems.evo.routing.router import RouterService
from systems.evo.schemas import (
    ConflictID,
    ConflictNode,
    EscalationRequest,
    EscalationResult,
    InnovationBrief,
    ObviousnessReport
)
from systems.nova.schemas import AuctionResult

class EvoEngine:
    """
    The central orchestrator for the Evo system. It composes all necessary
    sub-services and executes the conflict resolution lifecycle, respecting the
    strict Separation of Concerns defined in the EOS Bible. 
    """
    def __init__(self):
        # Service Composition: All dependencies are instantiated here.
        self.conflicts = ConflictsService()
        self.hypotheses = HypothesisService(conflict_getter=self.conflicts.get)
        self.obviousness = ObviousnessGate()
        self.assembler = ProposalAssembler()
        self.ledger = EvoLedger()

        # Bridge Composition: Outbound communication is handled by dedicated,
        # API-aware clients and routers, not direct HTTP calls. 
        self.router = RouterService() # For Atune/Equor communication 
        self.nova = NovaClient()       # For the Nova invention market 
        print("🚀 EvoEngine initialized with all subsystems and bridges.")

    def intake_conflicts(self, conflicts: list[ConflictNode | dict]) -> dict[str, Any]:
        """Intakes conflicts using the robust batching service."""
        return self.conflicts.batch(conflicts)

    async def run_cycle(self, conflict_ids: list[ConflictID], budget_ms: int | None = None) -> dict[str, Any]:
        """
        Runs a full cognitive cycle for a set of conflicts.
        It first checks for obviousness, and if not obvious, escalates to Nova.
        """
        conflict_nodes = [self.conflicts.peek(cid) for cid in conflict_ids]
        valid_nodes = [cn for cn in conflict_nodes if cn is not None]

        if not valid_nodes:
            return {"status": "error", "message": "No valid conflicts found."}

        # 1. Triage: Use the ObviousnessGate to decide if escalation is needed. 
        report = await self.obviousness.score_async(valid_nodes)
        if report.is_obvious:
            # TODO: Implement local repair logic.
            return {"status": "local_repair_pending", "obviousness": report.model_dump()}

        # 2. Escalate: If not obvious, proceed with escalation to Nova.
        req = EscalationRequest(conflict_ids=conflict_ids, budget_ms=budget_ms)
        esc_result = await self.escalate(req, report)
        
        # 3. Journaling: Record the final result.
        await self.ledger.record_escalation(esc_result)
        
        return {"status": "escalated_to_nova", "result": esc_result.model_dump()}

    async def escalate(self, request: EscalationRequest, report: ObviousnessReport) -> EscalationResult:
        """
        Orchestrates the escalation of a non-obvious conflict to the Nova market,
        adhering to all governance and communication protocols. 
        """
        decision_id = str(uuid.uuid4())
        brief: InnovationBrief | None = None
        
        try:
            # GOVERNANCE: Verify policy attestation with Equor before taking action. 
            # This is a placeholder for a real policy check.
            is_attested = await self.router.verify_policy_attestation(["evo_can_escalate"], decision_id)
            if not is_attested:
                raise RuntimeError("Escalation failed: Policy attestation denied by Equor.")

            # 1. Prepare Innovation Brief for Nova.
            brief = InnovationBrief(
                brief_id=f"evo-brief-{decision_id}",
                source="evo",
                problem="Resolve escalated system conflicts.",
                context={"conflict_ids": request.conflict_ids, **(request.brief_overrides or {})},
            )

            # 2. Run the Nova Market Triplet using the dedicated NovaClient. 
            candidates = await self.nova.propose(
                brief.model_dump(), decision_id=decision_id, budget_ms=request.budget_ms
            )
            if not candidates:
                raise ValueError("Nova returned no candidates.")

            evaluated_candidates = await self.nova.evaluate(candidates)
            auction_result_dict = await self.nova.auction(
                evaluated_candidates, decision_id=decision_id, budget_ms=request.budget_ms
            )
            auction_result = AuctionResult(**auction_result_dict)

            return EscalationResult(
                decision_id=decision_id,
                report=report,
                brief_id=brief.brief_id,
                provenance={"source": "EvoEngine.escalate", "decision_id": decision_id},
                candidates=[c for c in evaluated_candidates],
                auction=auction_result,
            )

        except Exception as e:
            # GRACEFUL FAILURE: Always return a schema-valid result, even in an error state. 
            return EscalationResult(
                decision_id=decision_id,
                report=report,
                brief_id=brief.brief_id if brief else f"evo-brief-fallback-{decision_id}",
                provenance={"error": str(e), "traceback": traceback.format_exc(), "decision_id": decision_id},
                candidates=[],
                auction=AuctionResult(winners=[], market_receipt={"error": "Escalation failed"}),
            )