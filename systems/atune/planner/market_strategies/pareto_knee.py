# systems/atune/planner/market_strategies/pareto_knee.py
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from systems.atune.budgeter.manager import AttentionBudgetManager
from systems.atune.planner.fae import FAEScore

# Import Bid for typing only to avoid runtime circular import.
if TYPE_CHECKING:
    from systems.atune.planner.market import Bid


def _fae_scalar(fae: FAEScore) -> float:
    """
    Robustly extract a scalar from FAEScore without assuming exact field names.
    Tries common attributes; falls back to float(...) if supported; else 0.0.
    """
    for attr in ("score", "total", "value", "fae", "u"):
        v = getattr(fae, attr, None)
        if isinstance(v, int | float):
            return float(v)
    try:
        return float(fae)  # type: ignore[arg-type]
    except Exception:
        return 0.0


def select_with_pareto_knee(
    bids: Sequence[Bid],
    budget_ms: int,
    manager: AttentionBudgetManager | None = None,
) -> list[Bid]:
    """
    Budget-feasible selection with a simple efficiency heuristic that approximates a Pareto knee:
      1) Compute efficiency = fae_scalar / (cost_ms + ε)
      2) Greedily take highest efficiency until budget is exhausted
    Note: This avoids runtime imports from market.py (no circular), while keeping strong type hints.
    """
    if budget_ms <= 0:
        return []

    epsilon = 1e-6
    scored = [
        (idx, _fae_scalar(b.fae_score), max(1, int(getattr(b, "estimated_cost_ms", 0) or 0)))
        for idx, b in enumerate(bids)
    ]
    # efficiency = value / cost
    scored.sort(key=lambda t: (t[1] / (t[2] + epsilon)), reverse=True)

    selected: list[Bid] = []
    cost_acc = 0
    for idx, val, cost in scored:
        if cost_acc + cost > budget_ms:
            continue
        selected.append(bids[idx])
        cost_acc += cost
        if cost_acc >= budget_ms:
            break

    return selected
