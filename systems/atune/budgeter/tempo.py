# systems/atune/budgeter/tempo.py
from __future__ import annotations

from collections import defaultdict

from systems.atune.budgeter.manager import AttentionBudgetManager


class TempoForecaster:
    """
    EWMA arrival rate per event_type. Reserves budget proportionally.
    """

    def __init__(self, alpha: float = 0.2, max_reserve_frac: float = 0.6):
        self.alpha = alpha
        self.max_reserve_frac = max_reserve_frac
        self._ewma: dict[str, float] = defaultdict(float)

    def observe_event(self, event_type: str) -> None:
        self._ewma[event_type] = self._ewma[event_type] * (1.0 - self.alpha) + self.alpha * 1.0

    def forecast_and_reserve(self, budget_manager: AttentionBudgetManager) -> None:
        total_rate = sum(self._ewma.values()) or 1.0
        reserves: dict[str, int] = {}
        for et, rate in self._ewma.items():
            frac = (rate / total_rate) * self.max_reserve_frac
            reserves[et] = int(frac * budget_manager.pool_ms_per_tick)
        budget_manager.set_reserves(reserves)
