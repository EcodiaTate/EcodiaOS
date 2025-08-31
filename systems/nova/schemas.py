# file: systems/nova/schemas.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

VEC_DIM: int = 3072  # provenance logging when embeddings appear


class InnovationBrief(BaseModel):
    brief_id: str
    source: str  # evo|synapse|user|system
    problem: str
    context: dict[str, Any] = {}
    constraints: dict[str, Any] = {}
    success: dict[str, Any] = {}
    obligations: dict[str, list[str]] = {}
    fallback: dict[str, Any] = {}
    hints: dict[str, Any] = {}


class InventionArtifact(BaseModel):
    type: str  # code|dsl|policy|graph
    diffs: list[dict[str, Any]] = []


class InventionCandidate(BaseModel):
    candidate_id: str
    playbook: str
    artifact: InventionArtifact
    spec: dict[str, Any] = {}  # may embed MechanismSpec/CapabilitySpec dicts
    scores: dict[str, float] = {}
    evidence: dict[str, Any] = {}
    obligations: dict[str, list[str]] = {}
    rollback_contract: dict[str, Any] = {}
    provenance: dict[str, Any] = {}


class DesignCapsule(BaseModel):
    capsule_id: str
    brief: InnovationBrief
    playbook_dag: dict[str, Any] = {}
    artifacts: list[InventionArtifact] = []
    eval_logs: dict[str, Any] = {}
    counterfactuals: dict[str, Any] = {}
    costs: dict[str, Any] = {}
    barcodes: dict[str, str] = {}


class AuctionResult(BaseModel):
    winners: list[str]
    spend_ms: int
    market_receipt: dict[str, Any]


class RolloutRequest(BaseModel):
    candidate_id: str
    capability_spec: dict[str, Any]
    obligations: dict[str, list[str]] = {}
    proof: dict[str, Any] | None = None


class RolloutResult(BaseModel):
    status: str  # accepted|rejected|staged
    driver_name: str | None = None
    notes: str | None = None
