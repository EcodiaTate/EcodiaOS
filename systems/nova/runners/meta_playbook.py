from __future__ import annotations

from uuid import uuid4

from systems.nova.dsl.specs import CapabilitySpec, MechanismOp, MechanismSpec
from systems.nova.schemas import InnovationBrief, InventionArtifact, InventionCandidate


class MetaPlaybookComposer:
    """
    Simple meta composer that emits a tiny, valid DAG.
    No learning/state; it’s just a generator that can live beside existing playbooks.
    """

    name = "meta.compose"
    PRIMITIVES = [
        ("plan", {}),
        ("critique", {"mode": "socratic"}),
        ("repair", {"strategy": "patch"}),
        ("batch", {"size": 3}),
        ("route", {"by": "risk"}),
    ]

    async def run(self, brief: InnovationBrief, budget_ms: int = 0) -> list[InventionCandidate]:
        nodes = [MechanismOp(name=n, params=p) for (n, p) in self.PRIMITIVES]
        edges = [[0, 1], [1, 2], [0, 4]]
        mech = MechanismSpec(nodes=nodes, edges=edges)
        caps = CapabilitySpec(
            io={"input": "innovation.brief", "output": "invention.candidates"},
            rate_limits={"qps": 5, "burst": 10},
        )
        return [
            InventionCandidate(
                candidate_id=f"inv_{uuid4().hex[:10]}",
                playbook=self.name,
                artifact=InventionArtifact(type="dsl", diffs=[]),
                spec={"mechanism_graph": mech.dict(), "capability_spec": caps.dict()},
                scores={
                    "fae": 0.5,
                    "novelty": 0.85,
                    "risk": 0.30,
                    "cost_ms": float(budget_ms or 0),
                },
                evidence={"sketch": "meta-dag"},
                obligations={"pre": [], "post": ["tests.ok"]},
                rollback_contract={"type": "undo", "params": {}},
                provenance={"brief_id": brief.brief_id},
            ),
        ]
