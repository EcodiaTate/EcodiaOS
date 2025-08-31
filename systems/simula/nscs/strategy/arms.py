from __future__ import annotations

from systems.synapse.core.registry import arm_registry


def _register():
    arm_registry.register(
        id="strategy/spec_ir_cgrag_v1",
        desc="Spec→SIM-IR→Python with contract-aware context; tests-first; SMT-lite",
        params={"planner": "tree", "retrieval": "contract-graph", "repair": "self-edit-diff"},
    )
    arm_registry.register(
        id="strategy/ir_refactor_semantic_v2",
        desc="Graph-preserving refactors; coverage-diff; twin replay",
        params={"refactor": "graph-preserving", "verify": "coverage-diff"},
    )


try:
    _register()
except Exception:
    pass
