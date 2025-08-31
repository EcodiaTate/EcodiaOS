from __future__ import annotations

from enum import Enum
from time import time
from typing import Any, Literal

from pydantic import BaseModel, Field
from systems.nova.schemas import AuctionResult 

# --------- IDs ----------
ConflictID = str
HypothesisID = str
EvidenceID = str
ProposalID = str
ReplayCapsuleID = str
TicketID = str
PatchID = str
MutationID = str
CapabilityID = str
SkillID = str


# --------- Core enums ----------
class ConflictKind(str, Enum):
    failure = "failure"
    disagreement = "disagreement"
    followup = "followup"
    drift = "drift"
    perf_regression = "perf_regression"
    safety_breach = "safety_breach"


class ConflictStatus(str, Enum):
    open = "open"
    in_review = "in_review"
    resolved = "resolved"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class DecisionConfidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# --------- Aux models ----------
class Reproducer(BaseModel):
    kind: Literal["unit", "integration", "sim"] = "unit"
    capsule_id: str | None = None
    minimal: bool = False
    stable: bool = False


class SpecCoverage(BaseModel):
    has_spec: bool = False
    gaps: list[Literal["temporal", "resource", "interface", "policy"]] = []


# --------- Data models ----------
class ConflictNode(BaseModel):
    conflict_id: ConflictID
    t_created: float = Field(default_factory=time)
    source_system: str
    kind: str # Simplified for compatibility
    description: str
    context: dict = Field(default_factory=dict)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    status: ConflictStatus = ConflictStatus.open
    # Other fields omitted for brevity but present in the full schema
    provenance: dict = Field(default_factory=dict)


class Hypothesis(BaseModel):
    hypothesis_id: HypothesisID
    conflict_ids: list[ConflictID]
    title: str
    rationale: str
    strategy: str
    scope_hint: dict = Field(default_factory=dict)
    expected_impact: dict = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    evidence_id: EvidenceID
    hypothesis_id: HypothesisID
    tests: dict = Field(default_factory=dict)
    fuzzing: dict = Field(default_factory=dict)
    invariants: dict = Field(default_factory=dict)
    protocol_checks: dict = Field(default_factory=dict)
    forecasts: dict = Field(default_factory=dict)
    diff_risk: dict = Field(default_factory=dict)
    replay_capsule_id: ReplayCapsuleID | None = None
    # Optional: tournament metadata when evidence comes from self-play
    tournament: dict[str, Any] = Field(default_factory=dict)


class Proposal(BaseModel):
    proposal_id: ProposalID
    title: str
    summary: str
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    evidence: list[EvidenceBundle] = Field(default_factory=list)
    change_sets: dict = Field(default_factory=dict)
    spec_impact_table: dict = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.medium
    risk_envelope: dict = Field(default_factory=dict)
    rollback_plan: dict = Field(default_factory=dict)
    telemetry_hooks: dict = Field(default_factory=dict)
    replay_capsules: list[ReplayCapsuleID] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)


# Back-compat alias
class EvolutionProposal(Proposal):
    pass


class ObviousnessReport(BaseModel):
    """
    The formal output from the ObviousnessGate, used throughout Evo.
    
    """
    conflict_ids: list[ConflictID]
    is_obvious: bool
    score: float
    confidence: float
    model_version: str
    contributing_features: dict[str, float] = Field(default_factory=dict)
    reason: str = ""


class EscalationResult(BaseModel):
    """
    The final, structured result of a successful escalation cycle.
    This is the data contract the EvoEngine's escalate method MUST return.
    
    """
    decision_id: str
    report: ObviousnessReport
    brief_id: str
    provenance: dict = Field(default_factory=dict)
    candidates: list[dict] = Field(default_factory=list) # Summaries of InventionCandidates
    auction: AuctionResult

class EscalationRequest(BaseModel):
    conflict_ids: list[ConflictID]
    brief_overrides: dict = Field(default_factory=dict)
    budget_ms: int | None = None

class ReplayCapsule(BaseModel):
    """Self-contained, reproducible record of an Evo cognitive cycle."""

    capsule_id: str = Field(description="Typically the decision_id.")
    barcode: str = Field(description="Stable hash of the capsule for integrity.")

    class Inputs(BaseModel):
        conflict_ids: list[ConflictID]
        initial_conflicts: list[ConflictNode] = Field(description="Conflicts at cycle start.")

    class Versions(BaseModel):
        evo_engine: str = "2.1"
        obviousness_model: str
        hypothesis_model: str

    class Artifacts(BaseModel):
        obviousness_report: ObviousnessReport
        hypotheses: list[Hypothesis]

    inputs: Inputs
    versions: Versions
    artifacts: Artifacts


class WhyTrace(BaseModel):
    decision_id: str
    stage: str
    verdict: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time)


class InnovationBrief(BaseModel):
    brief_id: str
    source: Literal["evo", "synapse", "user", "system"] = "evo"
    problem: str
    context: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)
    success: dict = Field(default_factory=dict)
    obligations: dict = Field(default_factory=dict)
    fallback: dict = Field(default_factory=dict)
    hints: dict = Field(default_factory=dict)


# --------- Ability / Evolution memory ----------
class CapabilitySpec(BaseModel):
    capability_id: CapabilityID
    name: str
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    invariants: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class SkillProfile(BaseModel):
    """Aggregate performance for a capability (rolling)."""

    skill_id: SkillID
    capability_id: CapabilityID
    successes: int = 0
    failures: int = 0
    avg_latency_ms: float = 0.0
    last_updated: float = Field(default_factory=time)


class PatchCandidate(BaseModel):
    patch_id: PatchID
    hypothesis_id: HypothesisID
    patch_diff: str
    score: float = 0.0
    meta: dict[str, Any] = Field(default_factory=dict)


class MutationRecord(BaseModel):
    mutation_id: MutationID
    decision_id: str
    patch_id: PatchID
    outcome: Literal["accepted", "rejected", "neutral"]
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time)
