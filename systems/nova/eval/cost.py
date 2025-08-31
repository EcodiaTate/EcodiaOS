from __future__ import annotations

from typing import Any


def estimate_cost_ms(mech: dict[str, Any]) -> int:
    """
    Very conservative static cost proxy based on graph size.
    This does NOT execute anything; it's a hint used only if scores.cost_ms is missing.
    """
    nodes = mech.get("nodes", [])
    edges = mech.get("edges", [])
    n = max(1, len(nodes))
    e = max(0, len(edges))
    # Base ~ 5ms per node + 2ms per edge, squared penalty for high density
    base = 5 * n + 2 * e
    density = e / max(1, n - 1)
    penalty = int(10 * (density**2))
    return int(base + penalty)
