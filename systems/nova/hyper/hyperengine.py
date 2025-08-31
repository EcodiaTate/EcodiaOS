# file: systems/nova/hyper/hyperengine.py
from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, PrivateAttr

from systems.nova.ledger.journal import write_capsule, write_whytrace
from systems.nova.ledger.ledger import NovaLedger
from systems.nova.memory.qora_bridge import QoraBridge
from systems.nova.proof.pcc_ext import ProofVMExt
from systems.nova.runners.auction_client import AuctionClient
from systems.nova.runners.eval_runner import EvalRunner
from systems.nova.runners.patch_handoff import PatchHandoff
from systems.nova.runners.portfolio_runner import PortfolioRunner
from systems.nova.schemas import (
    AuctionResult,
    DesignCapsule,
    InnovationBrief,
    InventionCandidate,
)


class NovaHyperEngine(BaseModel):
    """
    End-to-end orchestrator:
     - portfolio propose -> evaluate -> auction -> patch handoff
     - why-trace + capsule journalling + optional Qora persistence
    """

    # Pydantic v2 config: allow arbitrary runtime types on private attrs
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    # Runtime-only components (kept out of OpenAPI/JSON via PrivateAttr)
    _portfolio: PortfolioRunner = PrivateAttr(default_factory=PortfolioRunner)
    _eval: EvalRunner = PrivateAttr(default_factory=EvalRunner)
    _auction: AuctionClient = PrivateAttr(default_factory=AuctionClient)
    _handoff: PatchHandoff = PrivateAttr(default_factory=PatchHandoff)
    _pcc: ProofVMExt = PrivateAttr(default_factory=ProofVMExt)
    _ledger: NovaLedger = PrivateAttr(default_factory=NovaLedger)
    _qora: QoraBridge = PrivateAttr(default_factory=QoraBridge)

    async def propose(
        self,
        brief: InnovationBrief,
        *,
        budget_ms: int | None,
        decision_id: str,
    ) -> list[InventionCandidate]:
        return await self._portfolio.run(
            brief,
            budget_ms=int(budget_ms or 5000),
            decision_id=decision_id,
        )

    async def evaluate(self, candidates: list[InventionCandidate]) -> list[InventionCandidate]:
        # Let existing EvalRunner attach evidence/counterfactuals; preserve PCC hooks later
        return await self._eval.evaluate(candidates)

    async def auction(
        self,
        evaluated: list[InventionCandidate],
        *,
        budget_ms: int | None,
        decision_id: str,
    ) -> AuctionResult:
        return await self._auction.run(
            evaluated,
            budget_ms=int(budget_ms or 1000),
            decision_id=decision_id,
        )

    async def run_end_to_end(
        self,
        brief: InnovationBrief,
        *,
        budget_ms: int = 8000,
        decision_id: str | None = None,
    ) -> dict[str, Any]:
        decision = decision_id or f"nova_{uuid4().hex[:10]}"
        why: dict[str, Any] = {
            "brief_id": brief.brief_id,
            "playbooks_used": [],
            "provenance": {"decision_id": decision},
        }

        # PROPOSE
        cands = await self.propose(brief, budget_ms=int(0.6 * budget_ms), decision_id=decision)
        why["playbooks_used"] = sorted(
            {c.provenance.get("portfolio_arm", "unknown") for c in cands},
        )

        # EVALUATE
        evald = await self.evaluate(cands)

        # PCC SAFETY
        safe: list[InventionCandidate] = []
        for c in evald:
            proof_res = self._pcc.check(
                capability_spec=c.spec.get("capability_spec", {}),
                obligations=c.obligations or {},
                evidence=c.evidence or {},
                brief_success=getattr(brief, "success", {}) or {},
            )
            if proof_res.ok:
                safe.append(c)

        # AUCTION
        auction_res = await self.auction(safe, budget_ms=int(0.2 * budget_ms), decision_id=decision)
        winner_ids = set(auction_res.winners or [])
        winners = [c for c in safe if c.candidate_id in winner_ids]

        # CAPSULE + JOURNAL
        capsule: DesignCapsule = await self._ledger.save_capsule(
            brief=brief,
            artifacts=[w.artifact for w in winners],
            playbook_dag={"portfolio": why["playbooks_used"]},
            eval_logs={},
        )
        await write_capsule(capsule.model_dump())
        await write_whytrace(why)

        # QORA (optional)
        try:
            await self._qora.upsert(
                labels=["DesignCapsule", "Nova"],
                properties={
                    "capsule_id": capsule.capsule_id,
                    "body": capsule.model_dump(),
                },
            )
        except Exception:
            # Non-fatal persistence failure should not abort the pipeline
            pass

        # HANDOFF (don’t ship here; just return the ticket builder)
        return {
            "decision_id": decision,
            "capsule_id": capsule.capsule_id,
            "winners": [w.candidate_id for w in winners],
            "portfolio": why["playbooks_used"],
            "auction": auction_res.model_dump(),
        }
