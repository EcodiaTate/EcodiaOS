from __future__ import annotations

from typing import Any


class LintIssue(Exception):
    """Raised for structural errors that make a MechanismSpec invalid."""

    pass


def _has_cycle(n: int, edges: list[list[int]]) -> bool:
    g: dict[int, list[int]] = {i: [] for i in range(n)}
    indeg = [0] * n
    for a, b in edges:
        g[a].append(b)
        indeg[b] += 1
    q = [i for i, d in enumerate(indeg) if d == 0]
    seen = 0
    while q:
        u = q.pop(0)
        seen += 1
        for v in g[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return seen != n


def lint_mechanism(mech: dict[str, Any]) -> list[str]:
    """
    Static checks for MechanismSpec DAGs.
    Returns warnings; raises LintIssue on hard errors.
    """
    warnings: list[str] = []
    nodes = mech.get("nodes", [])
    edges = mech.get("edges", [])
    if not nodes:
        raise LintIssue("mechanism.nodes.empty")

    n = len(nodes)
    for e in edges:
        if not (isinstance(e, list) and len(e) == 2):
            raise LintIssue("mechanism.edges.bad_format")
        if not (0 <= e[0] < n and 0 <= e[1] < n):
            raise LintIssue("mechanism.edges.out_of_bounds")

    if _has_cycle(n, edges):
        raise LintIssue("mechanism.graph.cycle")

    # Soft suggestions (don’t fail)
    names = [str(nx.get("name", "")).strip().lower() for nx in nodes]
    if "critique" not in names:
        warnings.append("suggest.critique.missing")
    if "repair" not in names and "critique" in names:
        warnings.append("suggest.repair.after_critique")
    return warnings
