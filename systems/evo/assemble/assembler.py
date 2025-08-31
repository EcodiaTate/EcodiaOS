# file: systems/evo/assemble/assembler.py
from __future__ import annotations

from uuid import uuid4

from systems.evo.schemas import EvidenceBundle, Hypothesis, Proposal, ProposalID


class ProposalAssembler:
    def __init__(self) -> None:
        self._proposals: dict[ProposalID, Proposal] = {}

    def assemble(
        self,
        hypotheses: list[Hypothesis],
        evidence: list[EvidenceBundle],
        title: str,
        summary: str,
    ) -> Proposal:
        pid: ProposalID = f"pp_{uuid4().hex[:10]}"
        p = Proposal(
            proposal_id=pid,
            title=title,
            summary=summary,
            hypotheses=hypotheses,
            evidence=evidence,
            change_sets={},  # Simula will materialize diffs
            spec_impact_table={},
        )
        self._proposals[pid] = p
        return p

    def validate_completeness(self, p: Proposal) -> None:
        # Ensure structure is present; semantic checks live in Nova/Equor.
        assert p.title and p.summary is not None

    def get(self, proposal_id: ProposalID) -> Proposal | None:
        return self._proposals.get(proposal_id)

    def handover(self, proposal_id: ProposalID) -> dict:
        if proposal_id not in self._proposals:
            return {"handover_ref": None}
        # Handovers in Evo are metadata-only; Simula owns patching.
        return {"handover_ref": f"proposal://{proposal_id}"}
