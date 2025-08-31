# file: systems/nova/playbooks/tot_mcts.py
from __future__ import annotations

from uuid import uuid4

from ..schemas import InnovationBrief, InventionArtifact, InventionCandidate


class ToTMCTSPlaybook:
    name = "tot.mcts"

    async def run(self, brief: InnovationBrief, budget_ms: int = 0) -> list[InventionCandidate]:
        cand = InventionCandidate(
            candidate_id=f"inv_{uuid4().hex[:10]}",
            playbook=self.name,
            artifact=InventionArtifact(type="dsl", diffs=[]),
            spec={
                "mechanism_graph": {"ops": ["plan", "critique", "repair"]},
                "capability_spec": {},
            },
            scores={"fae": 0.58, "novelty": 0.52, "risk": 0.30, "cost_ms": float(budget_ms or 0)},
            evidence={"tests": {}, "ablations": {}, "proofs": {}},
            obligations={"pre": [], "post": []},
            rollback_contract={"type": "undo", "params": {}},
            provenance={"brief_id": brief.brief_id},
        )
        return [cand]
