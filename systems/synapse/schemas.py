# systems/synapse/schemas.py
# DEFINITIVE FINAL VERSION — with arm-style metadata, bandit diagnostics, and explicit TaskContext.metadata
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from systems.synapse.policy.policy_dsl import PolicyGraph

# --- Common Reusable Models ---
# systems/synapse/schemas.py
# --- APPEND: PolicyArm schema model (migrated from registry) ---


class PolicyArmModel(BaseModel):
    """
    Lightweight schema representation of a PolicyArm, used for serialization
    and DB round-trips. Mirrors the runtime PolicyArm class in registry.
    """

    id: str = Field(..., description="Unique arm identifier")
    mode: str = Field(default="generic", description="Operational mode of the arm")
    policy_graph: PolicyGraph
    A: Any | None = None
    A_shape: Any | None = None
    b: Any | None = None
    b_shape: Any | None = None


class TaskContext(BaseModel):
    """A consistent context object for tasks passed between systems."""

    model_config = ConfigDict(extra="allow")  # Pydantic v2 style

    task_key: str = Field(
        ...,
        description="Stable identifier for the task, e.g., 'simula_code_evolution'.",
    )
    goal: str = Field(..., description="The natural language objective of the task.")
    risk_level: Literal["low", "medium", "high"] = Field(
        "medium",
        description="The explicit risk level for this decision.",
    )
    budget: Literal["constrained", "normal", "extended"] = Field(
        "normal",
        description="Resource budget for the task.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Arbitrary structured context (memory bundles, user/session, etc.).",
    )


class HintRequest(BaseModel):
    """The request body for a hint."""

    namespace: str
    key: str
    context: dict[str, Any] = Field(default_factory=dict)


class HintResponse(BaseModel):
    """The response payload for a hint."""

    value: Any | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class Candidate(BaseModel):
    """Represents a candidate action or patch from a client system like Simula/Voxis."""

    id: str = Field(..., description="A unique identifier for this candidate.")
    content: dict[str, Any] = Field(
        ...,
        description="The candidate payload, e.g., a tool spec or code diff.",
    )


# --- API-Specific Schemas ---


class SelectArmRequest(BaseModel):
    task_ctx: TaskContext
    candidates: list[Candidate]


class ArmScore(BaseModel):
    """
    Represents a scored policy arm.

    Enhancements:
    - content: optional dynamic payload (e.g., an LLM-generated EosPlan for Voxis).
    - confidence: optional model- or heuristic-derived confidence in this arm.
    - bandit_meta: optional diagnostics from selection (features checksum, UCB parts, etc.).
    - policy_graph_meta: optional style/behavior hints derived from the chosen policy graph.
    - arm_style: optional alias for style hints (kept for convenience in downstream templates).
    """

    arm_id: str
    score: float
    reason: str
    content: dict[str, Any] | None = Field(
        default=None,
        description="Optional dynamic content, like a generated plan (EosPlan JSON).",
    )
    confidence: float | None = Field(
        default=None,
        description="Optional confidence for this arm (0–1).",
    )
    bandit_meta: dict[str, Any] | None = Field(
        default=None,
        description="Selection diagnostics: context_features_checksum, ucb_terms, etc.",
    )
    policy_graph_meta: dict[str, Any] | None = Field(
        default=None,
        description="Hints distilled from the policy graph to guide tone/tool tendencies.",
    )
    arm_style: dict[str, Any] | None = Field(
        default=None,
        description="Alias for style hints; same shape as policy_graph_meta.",
    )


class SelectArmResponse(BaseModel):
    """The definitive response from the select_arm/plan endpoints."""

    episode_id: str
    champion_arm: ArmScore
    shadow_arms: list[ArmScore]


class SimulateRequest(BaseModel):
    policy_graph: PolicyGraph
    task_ctx: TaskContext


class SimulateResponse(BaseModel):
    p_success: float
    delta_cost: float
    p_safety_hit: float
    sigma: float


class SMTCheckRequest(BaseModel):
    policy_graph: PolicyGraph


class SMTCheckResponse(BaseModel):
    ok: bool
    reason: str


class BudgetResponse(BaseModel):
    tokens_max: int
    wall_ms_max: int
    cpu_ms_max: int


class ExplainRequest(BaseModel):
    task_ctx: TaskContext
    ranked_arms: list[ArmScore]


class ExplainResponse(BaseModel):
    minset: list[str]
    flip_to_arm: str


class LogOutcomeRequest(BaseModel):
    episode_id: str
    task_key: str
    metrics: dict[str, Any]
    simulator_prediction: dict[str, Any] | None = None


class LogOutcomeResponse(BaseModel):
    ack: bool
    ingested_at: str


class PreferenceIngest(BaseModel):
    task_key: str
    a_episode_id: str
    b_episode_id: str
    winner: Literal["A", "B"]


class ContinueRequest(BaseModel):
    episode_id: str
    last_step_outcome: dict[str, Any] = Field(..., description="Metrics from the completed step.")


class ContinueResponse(BaseModel):
    episode_id: str
    next_action: ArmScore | None
    is_complete: bool


class RepairRequest(BaseModel):
    """The agent sends this when a step in a multi-step skill fails."""

    episode_id: str = Field(..., description="The episode ID of the ongoing, failed skill.")
    failed_step_index: int
    error_observation: dict[str, Any] = Field(
        ...,
        description="The error message or failed test results.",
    )


class RepairResponse(BaseModel):
    """Synapse's response with a suggested one-shot repair action."""

    episode_id: str
    repair_action: ArmScore
    notes: str


class EpisodeSummary(BaseModel):
    """A compact summary of an episode for comparison."""

    episode_id: str
    goal: str
    champion_arm_id: str
    reward_scalar: float
    reward_vector: list[float]
    outcome_summary: dict[str, Any]


class ComparisonPairResponse(BaseModel):
    """The two episodes to be compared by a human."""

    episode_a: EpisodeSummary
    episode_b: EpisodeSummary


class SubmitPreferenceRequest(BaseModel):
    """The human's choice."""

    winner_episode_id: str
    loser_episode_id: str
    reasoning: str | None = None


class PatchProposal(BaseModel):
    """A proposal for a self-upgrade, submitted by an agent like Simula."""

    summary: str = Field(..., description="A one-line summary of the proposed change.")
    diff: str = Field(..., description="The unified diff text of the code change.")
    source_agent: str = Field("Simula", description="The agent proposing the change.")
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Supporting evidence from sandbox tests.",
    )


# --- Policy Config (formerly "Policy Hint"; used by sdk/hint_ext.py) ---


class PolicyConfigRequest(BaseModel):
    """
    Request for a tuned policy configuration for a given task.
    Flexible by design: extra fields are allowed so upstream components can pass rich context.
    """

    model_config = ConfigDict(extra="allow")  # Pydantic v2 style

    task_key: str = Field(
        ...,
        description="Task identifier requesting a hint/config, e.g., 'atune.policy'.",
    )
    goal: str = Field(..., description="The natural-language objective for this config.")
    risk_level: Literal["low", "medium", "high"] = Field("medium")
    budget: Literal["constrained", "normal", "extended"] = Field("normal")
    mode_hint: str | None = Field(
        default=None,
        description="Optional caller-preferred cognitive mode.",
    )


class PolicyConfigResponse(BaseModel):
    """
    Tuned policy selection/config response.
    Mirrors what handle_policy_hint returns in sdk/hint_ext.py.
    """

    episode_id: str
    arm_id: str
    model: str
    temperature: float
    max_tokens: int
    search_depth: int
    verifier_set: str
    plan_style: str
    scores: dict[str, Any] = Field(default_factory=dict)
    explanation: dict[str, Any] = Field(default_factory=dict)
