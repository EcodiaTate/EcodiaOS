from __future__ import annotations

from typing import Any
from uuid import uuid4

from systems.nova.clients.equor_client import EquorPolicyClient
from systems.nova.clients.simula_client import SimulaClient
from systems.nova.ledger.ledger import NovaLedger
from systems.nova.proof.pcc_ext import ProofVMExt
from systems.nova.schemas import (
    AuctionResult,
    InnovationBrief,
    InventionCandidate,
)
from systems.nova.types.patch import SimulaPatchBrief, SimulaPatchTicket


class WinnerPipeline:
    """
    Nova's 'winner' pipeline:
      1) Selects the winner from the AuctionResult.
      2) Runs PCC (ProofVMExt) for structural/contract validation + extra safeguards.
      3) Queries Equor for identity and policy validation.
      4) Builds and submits a SimulaPatchBrief for sandboxed implementation.
      5) Persists a comprehensive DesignCapsule for replayability and audit.
    """

    def __init__(self) -> None:
        self._pvm = ProofVMExt()
        self._equor = EquorPolicyClient()
        self._simula = SimulaClient()
        self._ledger = NovaLedger()

    async def run(
        self,
        *,
        brief: InnovationBrief,
        candidates: list[InventionCandidate],
        auction: AuctionResult,
        decision_id: str | None = None,
        env_pins: dict[str, Any] | None = None,
        seeds: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        winners = self._pick_winners(candidates, auction)
        if not winners:
            return {"ok": False, "reason": "no_winners_in_auction_result"}

        # Currently processes the top winner; can be extended for portfolio rollouts
        winner = winners[0]
        decision_id = decision_id or f"dec_{uuid4().hex[:12]}"

        # Stage 1: Proof-Carrying Code Validation (with extra guards)
        brief_success = getattr(brief, "success", None)  # optional superset check if present
        proof_res = self._pvm.check(
            capability_spec=winner.spec.get("capability_spec", {}),
            obligations=winner.obligations,
            evidence=winner.evidence,
            brief_success=brief_success,
        )
        if not proof_res.ok:
            return {"ok": False, "stage": "proof_validation", "details": proof_res.model_dump()}

        # Stage 2: Equor Policy and Identity Validation
        policy_res = await self._equor.validate(
            payload={
                "capability_spec": winner.spec.get("capability_spec", {}),
                "obligations": winner.obligations,
                "identity_context": brief.context.get("identity", {}),
            },
            decision_id=decision_id,
        )
        if not policy_res.get("ok", False):
            return {"ok": False, "stage": "policy_validation", "details": policy_res}

        # Stage 3: Prepare and Submit to Simula
        patch_brief = self._build_simula_patch_brief(brief, winner, decision_id)
        simula_ticket: SimulaPatchTicket = await self._simula.submit_patch(
            patch_brief,
            decision_id=decision_id,
        )

        # Stage 4: Archive a comprehensive DesignCapsule
        design_capsule = await self._ledger.save_capsule(
            brief=brief,
            artifacts=[winner.artifact],
            playbook_dag={"playbook": winner.playbook, "provenance": winner.provenance},
            eval_logs={"final_scores": winner.scores, "evidence": winner.evidence},
            counterfactuals={"proof_result": proof_res.model_dump(), "policy_result": policy_res},
            costs={
                "auction_spend_ms": auction.spend_ms,
                "estimated_invention_cost_ms": winner.scores.get("cost_ms", 0),
            },
            env_pins=env_pins or {},
            seeds=seeds or {},
        )

        return {
            "ok": True,
            "decision_id": decision_id,
            "winner_id": winner.candidate_id,
            "simula_ticket": simula_ticket.model_dump(),
            "design_capsule_id": design_capsule.capsule_id,
        }

    def _pick_winners(
        self,
        candidates: list[InventionCandidate],
        auction: AuctionResult,
    ) -> list[InventionCandidate]:
        winner_ids = set(auction.winners or [])
        return [c for c in candidates if c.candidate_id in winner_ids]

    def _build_simula_patch_brief(
        self,
        brief: InnovationBrief,
        c: InventionCandidate,
        decision_id: str,
    ) -> SimulaPatchBrief:
        """Constructs the payload for the Simula handoff."""
        return SimulaPatchBrief(
            brief_id=f"sb_{decision_id}",
            source="nova",
            candidate_id=c.candidate_id,
            playbook=c.playbook,
            problem=brief.problem,
            context=brief.context,
            mechanism_spec=c.spec.get("mechanism_graph", {}),
            capability_spec=c.spec.get("capability_spec", {}),
            obligations=c.obligations,
            rollback_contract=c.rollback_contract,
            evidence=c.evidence,
            provenance={
                "nova_brief_id": brief.brief_id,
                "decision_id": decision_id,
                "invention_provenance": c.provenance,
            },
        )
