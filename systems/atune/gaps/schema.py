# systems/atune/gaps/schema.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RegretStats(BaseModel):
    window: int = Field(..., description="Number of recent trials considered")
    regret_avg: float = Field(..., description="Mean regret@compute over the window")
    regret_max: float = Field(..., description="Max regret@compute over the window")


class PostconditionFailure(BaseModel):
    code: str
    detail: str
    count: int


class ExemplarInput(BaseModel):
    description: str
    payload: dict[str, Any]


class CapabilityGapEvent(BaseModel):
    decision_id: str
    event_type: str = "capability_gap"
    # Either a capability is missing or chronically underperforming.
    missing_capability: str | None = None
    failing_capability: str | None = None
    # Optional hints for synthesis (when known)
    api_spec_url: str | None = None
    doc_urls: list[str] = Field(default_factory=list)
    # Context for synthesis/evaluation
    exemplars: list[ExemplarInput] = Field(default_factory=list)
    whytrace_barcodes: list[str] = Field(default_factory=list)
    regret: RegretStats | None = None
    postcondition_violations: list[PostconditionFailure] = Field(default_factory=list)
    # Optional incumbent to A/B against
    incumbent_driver: str | None = None
    # Who observed/emitted the gap
    source: str = "atune"
    meta: dict[str, Any] = Field(default_factory=dict)
