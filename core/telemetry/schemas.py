# Canonical metric schema shared across EOS
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

MetricKind = Literal["counter", "gauge", "histogram"]


class MetricDatum(BaseModel):
    kind: MetricKind
    name: str
    value: float = 0.0
    unit: str = ""
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    # Canonical EOS tags
    system: str  # "nova" | "evo" | "simula" | "synapse" | ...
    subsystem: str  # "runners" | "loop" | "budget" | ...
    component: str  # "playbook_runner" | "allocator" | ...
    phase: str | None = None  # "propose" | "evaluate" | "auction" | "rollout" | ...
    # Correlation (use what's relevant)
    decision_id: str | None = None
    episode_id: str | None = None
    task_key: str | None = None
    capsule_id: str | None = None
    request_id: str | None = None
    # Low-cardinality extras
    tags: dict[str, Any] = Field(default_factory=dict)


class MetricBatch(BaseModel):
    events: list[MetricDatum]
