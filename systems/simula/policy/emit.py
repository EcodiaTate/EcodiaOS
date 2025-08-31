# systems/simula/policy/emit.py
# FINAL VERSION FOR PHASE III
from __future__ import annotations

import hashlib
from typing import Any

from systems.simula.policy.effects import extract_effects_from_diff
from systems.synapse.policy.policy_dsl import PolicyGraph, PolicyNode


def patch_to_policygraph(candidate: dict[str, Any]) -> PolicyGraph:
    """
    Translates a Simula candidate diff into a rich PolicyGraph by performing
    static analysis to infer the true effects of the code change.
    """
    diff_text = candidate.get("diff", "")
    inferred_effects = extract_effects_from_diff(diff_text)

    # Base effects for any git operation
    effects = {"write"}
    if inferred_effects.get("net_access"):
        effects.add("net_access")
    if inferred_effects.get("execution"):
        effects.add("execute")

    # The policy graph now reflects the analyzed effects of the specific patch
    graph_data = {
        "version": 1,
        "nodes": [
            PolicyNode(
                id="simula.apply_patch",
                type="tool",
                effects=list(effects),
                params={"diff_hash": hashlib.sha256(diff_text.encode()).hexdigest()},
            ),
            PolicyNode(
                id="simula.run_tests",
                type="tool",
                effects=["execute"],
                params={"suite": "ci"},
            ),
        ],
        "edges": [{"source": "simula.apply_patch", "target": "simula.run_tests"}],
        "constraints": [{"class": "danger", "smt": "(not (and write net_access))"}],
    }
    return PolicyGraph.model_validate(graph_data)
