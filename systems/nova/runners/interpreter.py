# file: systems/nova/dsl/interpreter.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .specs import CapabilitySpec, MechanismSpec


class Step(BaseModel):
    op: str
    params: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    steps: list[Step] = Field(default_factory=list)
    io_schema: dict[str, Any] = Field(default_factory=dict)


class MechanismInterpreter:
    """
    Deterministic interpreter for MechanismSpec → Plan.
    - Validates DAG cardinality (edges point to existing nodes)
    - Performs trivial op canonicalization (lowercase names)
    - Emits linearized plan (topological order) with attached IO schema
    """

    def compile(self, spec: MechanismSpec, cap: CapabilitySpec | None = None) -> Plan:
        # Validate nodes/edges
        n = len(spec.nodes or [])
        for e in spec.edges or []:
            if len(e) != 2 or not (0 <= e[0] < n and 0 <= e[1] < n):
                raise ValidationError(f"Invalid edge {e}", Plan)

        # Build adjacency + indegrees
        indeg = [0] * n
        adj: dict[int, list[int]] = {i: [] for i in range(n)}
        for u, v in spec.edges or []:
            adj[u].append(v)
            indeg[v] += 1

        # Kahn's topo sort
        q = [i for i in range(n) if indeg[i] == 0]
        order: list[int] = []
        while q:
            u = q.pop(0)
            order.append(u)
            for v in adj[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        if len(order) != n:
            raise ValidationError("Cycle detected in MechanismSpec", Plan)

        steps = [
            Step(op=(spec.nodes[i].name or "").lower(), params=spec.nodes[i].params or {})
            for i in order
        ]
        io_schema = cap.io if cap else {}
        return Plan(steps=steps, io_schema=io_schema)

    def simulate(self, plan: Plan, inputs: dict[str, Any]) -> dict[str, Any]:
        """
        Pure, side-effect free simulation stub:
        - Propagates inputs through steps by copying keys unless a step rewrites.
        - Each step may attach a _trace list for WhyTrace joins.
        """
        state = dict(inputs)
        trace = state.setdefault("_trace", [])
        for step in plan.steps:
            trace.append({"op": step.op, "params": step.params})
            # Example: simple routing ops annotate but do not mutate
            if step.op in {"route", "batch", "hedge", "plan", "critique", "repair"}:
                continue
            # Simple transforms (placeholder logic without external effects)
            if step.op == "extract" and "text" in state:
                state["tokens"] = state["text"].split()
            if step.op == "reify" and "tokens" in state:
                state["length"] = len(state["tokens"])
        return state
