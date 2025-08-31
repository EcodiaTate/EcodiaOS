# file: systems/evo/briefs/innovation.py
from __future__ import annotations

from typing import Any
from uuid import uuid4

from systems.evo.schemas import ConflictNode, ObviousnessReport


def build_innovation_brief(
    conflicts: list[ConflictNode],
    report: ObviousnessReport,
) -> dict[str, Any]:
    """
    Construct a Nova InnovationBrief dict from conflicts + obviousness report.
    Keeps Nova decoupled from Evo internals and respects role boundaries.
    """
    brief_id = f"br_{uuid4().hex[:10]}"
    problem = "; ".join([c.description for c in conflicts])[:4096]
    ctx = {
        "conflicts": [c.dict() for c in conflicts],
        "obviousness": report.dict(),
    }
    constraints = {
        "separation_of_concerns": True,
        "no_codegen_here": True,  # Simula will handle codegen after Atune decision
        "safety": {"equor_policy_required": True},
    }
    success = {"winners_at_k": 1, "replay_ready": True}
    return {
        "brief_id": brief_id,
        "source": "evo",
        "problem": problem,
        "context": ctx,
        "constraints": constraints,
        "success": success,
        "obligations": {"pre": [], "post": ["tests.ok", "invariants.checked"]},
        "fallback": {"type": "rollback", "params": {}},
        "hints": {},
    }
