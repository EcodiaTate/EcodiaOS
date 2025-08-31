# core/metrics/registry.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Counter:
    value: int = 0

    def inc(self, n: int = 1):
        self.value += n


@dataclass
class Gauge:
    value: float = 0.0

    def set(self, v: float):
        self.value = float(v)


@dataclass
class MetricsRegistry:
    counters: dict[str, Counter] = field(default_factory=dict)
    gauges: dict[str, Gauge] = field(default_factory=dict)

    def counter(self, name: str) -> Counter:
        self.counters.setdefault(name, Counter())
        return self.counters[name]

    def gauge(self, name: str) -> Gauge:
        self.gauges.setdefault(name, Gauge())
        return self.gauges[name]


REGISTRY = MetricsRegistry()
