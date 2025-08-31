from __future__ import annotations

from typing import Any
from uuid import uuid4

from systems.evo.schemas import EvidenceBundle, Hypothesis, Proposal, RiskLevel
from systems.evo.spec.deriver import SpecDeriver


class ProposalAssembler:
    """
    Satisfies /evo/proposals/* expectations:
      - assemble(hypotheses, evidence, title, summary) -> Proposal
      - validate_completeness(proposal)
      - get(proposal_id), handover(proposal_id)
    """

    def __init__(self) -> None:
        self._spec = SpecDeriver()
        self._store: dict[str, Proposal] = {}

    def assemble(
        self,
        hypotheses: list[Hypothesis],
        evidence: list[EvidenceBundle],
        title: str,
        summary: str,
    ) -> Proposal:
        pid = f"ep_{uuid4().hex[:10]}"

        obligations = self._spec.derive_obligations(
            [c for h in hypotheses for c in h.meta.get("conflicts", [])],
        )
        impact = self._spec.impact_table(obligations)

        change_sets: dict[str, Any] = {"plans": {}}
        for h in hypotheses:
            strat = h.strategy or "unspecified"
            slot = change_sets["plans"].setdefault(
                strat,
                {"files": [], "rationale": h.rationale, "scope_hint": h.scope_hint},
            )
            # attach patch hints if tests include a diff
            for e in evidence:
                if e.hypothesis_id == h.hypothesis_id:
                    diff = e.tests.get("patch_diff") if isinstance(e.tests, dict) else None
                    if diff:
                        slot.setdefault("patch_hints", []).append(diff)

        p = Proposal(
            proposal_id=pid,
            title=title,
            summary=summary,
            hypotheses=hypotheses,
            evidence=evidence,
            change_sets=change_sets,
            spec_impact_table=impact,
            rollback_plan=self._spec.derive_rollback(
                [c for h in hypotheses for c in h.meta.get("conflicts", [])],
            ),
            risk_level=self._score_risk(evidence, change_sets),
            risk_envelope={
                "blast_radius_modules": sorted(
                    {m for h in hypotheses for m in h.scope_hint.get("modules", [])},
                ),
            },
            telemetry_hooks={"metrics": ["actual_utility", "p95_latency_ms", "error_rate"]},
        )
        self._store[pid] = p
        return p

    def validate_completeness(self, p: Proposal) -> None:
        # Minimal guard-rails
        assert p.title and p.summary
        assert p.hypotheses and p.evidence

    def get(self, proposal_id: str) -> Proposal | None:
        return self._store.get(proposal_id)

    def handover(self, proposal_id: str) -> dict[str, Any]:
        # Placeholder: produce a stable handover ref usable by Nova/Nexus layers
        return {"handover_ref": f"handover:{proposal_id}"}

    def _score_risk(self, ev: list[EvidenceBundle], cs: dict[str, Any]) -> RiskLevel:
        modal = 0
        for e in ev:
            modal += sum(
                1
                for k in ("tests", "fuzzing", "invariants", "forecasts", "diff_risk")
                if getattr(e, k, None)
            )
        size_hint = sum(len(v.get("patch_hints", [])) for v in cs.get("plans", {}).values())
        score = max(0, 3 - modal) + (1 if size_hint > 10 else 0)
        return RiskLevel.low if score <= 1 else (RiskLevel.medium if score <= 2 else RiskLevel.high)
