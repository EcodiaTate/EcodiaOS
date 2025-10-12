# systems/axon/mesh/scorecard.py
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import quantiles
from typing import Deque

from pydantic import BaseModel, Field


class DriverScorecard(BaseModel):
    driver_name: str
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    average_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    average_uplift: float = 0.0
    last_seen_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def success_rate(self) -> float:
        return self.successful_runs / self.total_runs if self.total_runs > 0 else 0.0


@dataclass
class _RunSample:
    ok: bool
    latency_ms: float
    cost_usd: float
    uplift: float
    ts: float


class ScorecardManager:
    """
    Maintains scorecards + a bounded rolling window of recent runs per driver.
    """

    def __init__(self, window_max: int = 500) -> None:
        self._scorecards: dict[str, DriverScorecard] = {}
        self._history: dict[str, deque[_RunSample]] = {}
        self._window_max = window_max

    def update_scorecard(
        self,
        driver_name: str,
        was_successful: bool,
        latency_ms: float,
        cost_usd: float = 0.0,
        uplift: float = 0.0,
        ts: float | None = None,
    ) -> None:
        if driver_name not in self._scorecards:
            self._scorecards[driver_name] = DriverScorecard(driver_name=driver_name)
            self._history[driver_name] = deque(maxlen=self._window_max)

        card = self._scorecards[driver_name]
        # streaming avgs
        old_avg_latency = card.average_latency_ms
        old_avg_uplift = card.average_uplift
        card.total_runs += 1
        card.average_latency_ms += (latency_ms - old_avg_latency) / card.total_runs
        card.average_uplift += (uplift - old_avg_uplift) / card.total_runs
        if was_successful:
            card.successful_runs += 1
        else:
            card.failed_runs += 1
        card.total_cost_usd += cost_usd
        card.last_seen_utc = datetime.now(UTC).isoformat()

        self._history[driver_name].append(
            _RunSample(
                ok=was_successful,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                uplift=uplift,
                ts=ts or datetime.now(UTC).timestamp(),
            ),
        )

        print(f"ScorecardManager: Updated '{driver_name}'. SR={card.success_rate:.2%}")

    def get_all_scorecards(self) -> list[DriverScorecard]:
        return list(self._scorecards.values())

    # ---- new helpers for promoter/autoroller ----

    def get_scorecard(self, driver_name: str) -> DriverScorecard | None:
        return self._scorecards.get(driver_name)

    def get_window_metrics(self, driver_name: str, window_n: int = 200) -> dict[str, float] | None:
        hist = list(self._history.get(driver_name, ()))
        if not hist:
            return None
        window = hist[-window_n:] if window_n > 0 else hist
        latencies = [s.latency_ms for s in window]
        p95 = (
            quantiles(latencies, n=100)[94] if len(latencies) >= 20 else max(latencies)
        )  # rough but robust
        success_rate = sum(1 for s in window if s.ok) / len(window)
        avg_uplift = (sum(s.uplift for s in window) / len(window)) if window else 0.0
        return {
            "window_size": float(len(window)),
            "p95_ms": float(p95),
            "success_rate": float(success_rate),
            "avg_uplift": float(avg_uplift),
            "avg_latency_ms": float(sum(latencies) / len(latencies)),
        }
