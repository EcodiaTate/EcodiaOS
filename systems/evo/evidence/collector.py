from __future__ import annotations

import asyncio
from uuid import uuid4

from systems.evo.clients.simula_client import SimulaClient
from systems.evo.schemas import EvidenceBundle, Hypothesis, ReplayCapsuleID, TicketID


class EvidenceOrchestrator:
    """
    Episode-local evidence planner/collector.
    Sync surface (matches /evo/evidence/* endpoints) with async internals.
    """

    def __init__(self, decision_id: str | None = None) -> None:
        self._simula = SimulaClient()
        self._decision_id = decision_id or f"dec_{uuid4().hex[:10]}"
        self._tickets: dict[TicketID, Hypothesis] = {}

    def plan_suite(self, hypothesis: Hypothesis) -> dict:
        return {
            "steps": [
                {"kind": "codegen", "via": "simula.jobs.codegen"},
                {"kind": "validate", "via": "simula.jobs.codegen"},
                {"kind": "historical_replay", "via": "simula.historical-replay"},
            ],
            "hypothesis_id": hypothesis.hypothesis_id,
        }

    def request(self, hypothesis: Hypothesis) -> TicketID:
        tkt: TicketID = f"tkt_{uuid4().hex[:10]}"
        self._tickets[tkt] = hypothesis
        return tkt

    def collect(self, ticket_id: TicketID) -> EvidenceBundle:
        return asyncio.run(self._collect_async(ticket_id))

    async def _collect_async(self, ticket_id: TicketID) -> EvidenceBundle:
        hyp = self._tickets.get(ticket_id)
        if hyp is None:
            return EvidenceBundle(
                evidence_id=f"ev_{uuid4().hex[:10]}",
                hypothesis_id="unknown",
                tests={"ok": False},
            )

        patch = await self._simula.generate_patch_from_hypothesis(
            hypothesis_title=hyp.title,
            hypothesis_rationale=hyp.rationale,
            decision_id=self._decision_id,
        )
        patch_diff = patch.get("patch_diff", "")

        test_res = await self._simula.test_patch(patch_diff)
        tests = {
            "ok": bool(test_res.get("passed", False)),
            "details": test_res.get("reason", "n/a"),
            "patch_diff": patch_diff,
        }

        return EvidenceBundle(
            evidence_id=f"ev_{uuid4().hex[:10]}",
            hypothesis_id=hyp.hypothesis_id,
            tests=tests,
            diff_risk={"loc_changed": len(patch_diff.splitlines())},
        )

    def attach_replay_capsule(self, evidence: EvidenceBundle) -> ReplayCapsuleID:
        return ReplayCapsuleID(f"rc_{uuid4().hex[:10]}")
