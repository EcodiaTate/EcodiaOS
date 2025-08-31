from __future__ import annotations

from time import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from systems.evo.schemas import InnovationBrief


class TargetHint(BaseModel):
    path: str
    kind: Literal["file", "module", "test", "config", "auto"] = "auto"
    signature: str | None = None


class SimulaCodegenRequest(BaseModel):
    spec: str = Field(..., min_length=10)
    targets: list[TargetHint] = Field(default_factory=list)


class EquorAttestation(BaseModel):
    run_id: str = Field(default_factory=lambda: f"att_{uuid4().hex[:16]}")
    episode_id: str
    agent_name: str = "evo"
    timestamp: float = Field(default_factory=time)
    policy_names: list[str]
    context: dict[str, Any] = Field(default_factory=dict)


class RoutingError(Exception):
    def __init__(self, system: str, message: str, details: dict | None = None):
        self.system = system
        self.message = message
        self.details = details or {}
        super().__init__(f"[{system}] {message}")


class AtuneDeliberationRequest(BaseModel):
    brief: InnovationBrief
    budget_ms: int | None = None
    decision_id: str


class AtuneAttentionBid(BaseModel):
    source_event_id: str
    fae_score: dict[str, float]
    estimated_cost_ms: int
    action_details: dict[str, Any]
