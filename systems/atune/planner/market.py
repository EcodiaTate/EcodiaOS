# systems/atune/planner/market.py
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from systems.atune.budgeter.manager import AttentionBudgetManager
from systems.atune.planner.fae import FAEScore
from systems.atune.planner.market_strategies.pareto_knee import select_with_pareto_knee


@dataclass
class Bid:
    source_event_id: str
    fae_score: FAEScore
    estimated_cost_ms: int
    action_details: Any


def _resolve_budget_ms(
    budget: int | AttentionBudgetManager | None,
    default: int = 0,
) -> int:
    """
    Accept either a raw int or an AttentionBudgetManager and return an integer budget (ms).
    Tries common attr/method names; falls back to `default` if none found.
    """
    if budget is None:
        return max(0, int(default))
    if isinstance(budget, int):
        return max(0, budget)

    # Introspect manager fields that might exist
    for attr in ("available_ms", "remaining_ms", "window_ms", "budget_ms", "current_budget_ms"):
        try:
            v = getattr(budget, attr, None)
            if isinstance(v, int | float):
                return max(0, int(v))
        except Exception:
            pass

    # Introspect manager methods that might return a number
    for meth in ("available_ms", "get_available_ms", "get_window_budget_ms", "get_budget_ms"):
        try:
            f: Callable[[], Any] | None = getattr(budget, meth, None)  # type: ignore[assignment]
            if callable(f):
                v = f()
                if isinstance(v, int | float):
                    return max(0, int(v))
        except Exception:
            pass

    return max(0, int(default))


class AttentionMarket:
    """
    Thin orchestrator over selection strategies.
    Runtime deps flow outward (no strategies importing this module).
    """

    def __init__(self, budget_manager: AttentionBudgetManager | None = None) -> None:
        self.budget_manager = budget_manager

    def run_auction(
        self,
        bids: list[Bid],
        budget: int | AttentionBudgetManager | None,
        strategy: str = "pareto_knee",
    ) -> list[Bid]:
        """
        Select a set of bids under a time budget (ms).

        `budget` may be:
          - int: milliseconds
          - AttentionBudgetManager: we’ll introspect to derive ms
          - None: treated as 0 (no selections)
        """
        budget_ms: int = _resolve_budget_ms(budget, default=0)
        if budget_ms <= 0 or not bids:
            return []

        if strategy == "pareto_knee":
            return select_with_pareto_knee(bids, budget_ms, self.budget_manager)

        # Future strategies can be added here; default to pareto_knee semantics.
        return select_with_pareto_knee(bids, budget_ms, self.budget_manager)

    # Alias kept for API parity
    run_vcg_auction = run_auction
