from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    t: str  # ISO8601 date/time (UTC)
    value: float
    tags: dict[str, Any] = Field(default_factory=dict)


class MetricSeries(BaseModel):
    name: str
    system: str
    scope: str  # e.g., "llm", "nova", "eval", "axon"
    tags: dict[str, Any] = Field(default_factory=dict)
    points: list[MetricPoint] = Field(default_factory=list)


class MetricSeriesRequest(BaseModel):
    name: str
    scope: str | None = None  # e.g., "llm" or "nova"
    system: str | None = None  # evo|simula|nova|synapse|...
    days: int = 30
    group_by: str | None = None  # e.g., "provider", "model", "arm_id"


class AgentBadge(BaseModel):
    agent: str
    calls: int
    avg_latency_ms: float
    p95_latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    success_rate: float


class AgentsOverview(BaseModel):
    window_days: int
    agents: list[AgentBadge]
