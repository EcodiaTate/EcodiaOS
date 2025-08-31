# systems/atune/budgeter/manager.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AttentionBudgetManager:
    pool_ms_per_tick: int = 20000
    _available_ms: int = field(default=0, init=False)
    _reserves: dict[str, int] = field(default_factory=dict, init=False)  # event_type -> reserved ms
    _used_reserves: dict[str, int] = field(default_factory=dict, init=False)

    def set_pool_ms_per_tick(self, new_pool_ms: int) -> None:
        self.pool_ms_per_tick = max(0, int(new_pool_ms))

    def tick(self) -> None:
        self._available_ms = self.pool_ms_per_tick
        self._used_reserves = {k: 0 for k in self._reserves}

    def add_reserve(self, event_type: str, ms: int) -> None:
        self._reserves[event_type] = max(0, int(ms))

    def set_reserves(self, reserves: dict[str, int]) -> None:
        self._reserves = {k: max(0, int(v)) for k, v in reserves.items()}

    def get_available_budget(self) -> int:
        return max(0, int(self._available_ms))

    def request_allocation(self, ms: int, source: str = "", event_type: str | None = None) -> bool:
        ms = max(0, int(ms))
        if event_type and event_type in self._reserves:
            remaining_reserve = self._reserves[event_type] - self._used_reserves.get(event_type, 0)
            to_take = min(ms, max(0, remaining_reserve))
            self._used_reserves[event_type] = self._used_reserves.get(event_type, 0) + to_take
            ms -= to_take
        if ms <= self._available_ms:
            self._available_ms -= ms
            return True
        return False

    def can_allocate_non_reserved(self, ms: int) -> bool:
        return ms <= self._available_ms
