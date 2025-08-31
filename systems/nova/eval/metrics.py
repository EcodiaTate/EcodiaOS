from __future__ import annotations

from typing import Any


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def mechanism_complexity(mech: dict[str, Any]) -> float:
    n = len(mech.get("nodes", []))
    e = len(mech.get("edges", []))
    # Normalise: assume 1..20 nodes typical
    return _clamp((n + 0.5 * e) / 20.0)


def risk_hint(mech: dict[str, Any]) -> float:
    # Heuristic: deeper/denser graphs carry higher risk
    n = len(mech.get("nodes", []))
    e = len(mech.get("edges", []))
    depthish = e / max(1, n)
    return _clamp(0.2 + 0.6 * depthish)


def fae_composite(mech: dict[str, Any]) -> float:
    # Placeholder: without execution traces, derive a conservative proxy
    comp = mechanism_complexity(mech)
    risk = risk_hint(mech)
    return _clamp(0.65 * comp + 0.35 * (1.0 - risk))
