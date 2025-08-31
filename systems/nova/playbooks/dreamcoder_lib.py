# file: systems/nova/playbooks/dreamcoder_lib.py
from __future__ import annotations

from uuid import uuid4

from ..schemas import InnovationBrief, InventionArtifact, InventionCandidate


class DreamCoderLibraryPlaybook:
    name = "dreamcoder.library"

    async def run(self, brief: InnovationBrief, budget_ms: int = 0) -> list[InventionCandidate]:
        cand = InventionCandidate(
            candidate_id=f"inv_{uuid4().hex[:10]}",
            playbook=self.name,
            artifact=InventionArtifact(type="graph", diffs=[]),
            spec={
                "mechanism_graph": {"ops": ["extract", "reify", "prioritize"]},
                "capability_spec": {},
            },
            scores={"fae": 0.54, "novelty": 0.60, "risk": 0.26, "cost_ms": float(budget_ms or 0)},
            evidence={"tests": {}, "ablations": {}, "proofs": {}},
            obligations={"pre": [], "post": []},
            rollback_contract={"type": "undo", "params": {}},
            provenance={"brief_id": brief.brief_id},
        )
        return [cand]
