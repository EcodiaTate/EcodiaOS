# systems/atune/journal/why_helpers.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from systems.atune.planner.market import Bid


@dataclass
class _Point:
    i: int
    U: float  # utility (maximize)
    IG: float  # novelty/info gain (maximize)
    Risk: float  # risk (minimize)
    Cost: float  # cost ms (minimize)


def _terms(b: Bid) -> dict[str, float]:
    ts = getattr(b.fae_score, "terms", {}) or {}
    out = {k: float(v) for k, v in ts.items() if isinstance(v, int | float)}
    out.setdefault("Utility", float(getattr(b.fae_score, "final_score", 0.0)))
    out.setdefault("IG", float(out.get("Novelty", 0.0)))
    out.setdefault("Risk", float(out.get("Risk", 0.0)))
    return out


def _points(bids: list[Bid]) -> list[_Point]:
    pts: list[_Point] = []
    for i, b in enumerate(bids):
        ts = _terms(b)
        pts.append(
            _Point(
                i,
                U=ts["Utility"],
                IG=ts["IG"],
                Risk=ts["Risk"],
                Cost=float(b.estimated_cost_ms),
            ),
        )
    return pts


def _dominates(a: _Point, b: _Point) -> bool:
    return (a.U >= b.U and a.IG >= b.IG and a.Risk <= b.Risk and a.Cost <= b.Cost) and (
        a.U > b.U or a.IG > b.IG or a.Risk < b.Risk or a.Cost < b.Cost
    )


def _pareto_front(pts: list[_Point]) -> list[_Point]:
    front: list[_Point] = []
    for p in pts:
        if any(_dominates(q, p) for q in pts if q.i != p.i):
            continue
        front.append(p)
    return front


def _normalize(front: list[_Point]) -> list[tuple[int, float, float]]:
    U_vals, IG_vals = [p.U for p in front], [p.IG for p in front]
    R_vals, C_vals = [p.Risk for p in front], [p.Cost for p in front]

    def _norm(xs, maximize=True):
        lo, hi = min(xs), max(xs)
        if hi - lo < 1e-9:
            return [0.5] * len(xs)
        vals = [(x - lo) / (hi - lo) for x in xs]
        return vals if maximize else [1.0 - v for v in vals]

    U_n, IG_n = _norm(U_vals, True), _norm(IG_vals, True)
    R_n, C_n = _norm(R_vals, False), _norm(C_vals, False)
    return [
        (p.i, 0.5 * U_n[k] + 0.5 * IG_n[k], 0.5 * R_n[k] + 0.5 * C_n[k])
        for k, p in enumerate(front)
    ]


def _knee_index(front: list[_Point]) -> int:
    if not front:
        return -1
    norm = _normalize(front)  # (idx, Benefit, Cost)
    best, best_d = 0, 1e9
    for idx, B, C in norm:
        d = math.hypot(1.0 - B, 1.0 - C)  # distance to utopia (1,1)
        if d < best_d:
            best, best_d = idx, d
    # map back into front’s order
    for j, p in enumerate(front):
        if p.i == best:
            return j
    return 0


def summarize_pareto_knee(bids: list[Bid], winners: list[Bid]) -> dict[str, Any]:
    if not bids:
        return {
            "strategy": "pareto_knee",
            "explain": {"frontier": [], "knee_capability": None, "winners_count": 0},
        }

    pts = _points(bids)
    front = _pareto_front(pts)
    knee_j = _knee_index(front) if front else -1
    knee_idx = front[knee_j].i if (front and knee_j >= 0) else None
    knee_cap = (
        getattr(bids[knee_idx].action_details, "target_capability", None)
        if knee_idx is not None
        else None
    )

    table = [
        {
            "idx": p.i,
            "capability": getattr(bids[p.i].action_details, "target_capability", None),
            "U": round(p.U, 4),
            "IG": round(p.IG, 4),
            "Risk": round(p.Risk, 4),
            "Cost_ms": int(p.Cost),
            "winner": (bids[p.i] in winners),
            "is_knee": (p.i == knee_idx),
        }
        for p in front[:12]  # compact sample
    ]

    return {
        "strategy": "pareto_knee",
        "explain": {
            "knee_capability": knee_cap,
            "winners_count": len(winners),
            "frontier_sample": table,
        },
    }
