from __future__ import annotations

from typing import Any

from .dsl import SystemSpec


def compile_spec_to_constraints(spec: SystemSpec, target: str | None = None) -> dict[str, Any]:
    focus = [m for m in spec.modules if target is None or m.path == target]
    return {
        "targets": [m.path for m in focus],
        "apis": [{"path": m.path, "apis": [a.model_dump() for a in m.apis]} for m in focus],
        "invariants": [
            {"path": m.path, "invariants": [i.model_dump() for i in m.invariants]} for m in focus
        ],
        "perf": [{"path": m.path, "perf": m.perf.model_dump() if m.perf else None} for m in focus],
        "global_invariants": [i.model_dump() for i in spec.global_invariants],
    }
