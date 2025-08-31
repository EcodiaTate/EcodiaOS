# systems/equor/schemas.py

from typing import Any, Literal

try:
    from pydantic import BaseModel, Field
except Exception:  # allow v1 fallback if needed
    from pydantic.v1 import BaseModel, Field  # type: ignore

# A unique identifier for a node in the Neo4j graph.
NodeID = str


class Facet(BaseModel):
    """
    Represents a single, versioned aspect of identity (e.g., a style guide,
    an ethical principle, a mission statement).
    """

    id: NodeID | None = None
    name: str = Field(..., description="Unique, human-readable name for the facet.")
    version: str = Field(..., description="Version identifier (e.g., '1.0.0', '2025-08-20').")
    category: Literal[
        "affective",
        "ethical",
        "philosophical",
        "safety",
        "style",
        "voice",
        "mission",
        "operational",
        "compliance",
    ] = Field(..., description="The functional category of the facet.")
    text: str = Field(..., description="The full text content of the facet.")
    supersedes: NodeID | None = Field(
        None,
        description="The ID of the facet version this one replaces.",
    )


class ConstitutionRule(BaseModel):
    """
    A formal, versioned rule that constrains agent behavior.
    Rules have explicit precedence and conflict declarations.
    """

    id: NodeID | None = None
    name: str = Field(..., description="Unique, human-readable name for the rule.")
    version: str = Field(..., description="Version identifier.")
    priority: int = Field(..., ge=0, description="Execution priority (higher value runs first).")
    severity: Literal["low", "medium", "high", "critical"] = Field(
        ...,
        description="The severity of a breach.",
    )
    deontic: Literal["MUST", "SHOULD", "MAY"] = Field(
        ...,
        description="The modal force of the rule.",
    )
    text: str = Field(..., description="The full text of the rule.")
    predicate_dsl: str | None = Field(
        None,
        description="A machine-checkable predicate, e.g., 'context.risk_level < 0.8'.",
    )
    supersedes: str | None = Field(
        None,
        description="The ID of the rule version this one replaces.",
    )
    conflicts_with: list[NodeID] = Field(
        [],
        description="A list of rule IDs this rule is incompatible with.",
    )


class Profile(BaseModel):
    """
    A named collection of facets and rules that defines the identity
    for a specific agent in a specific context (e.g., 'Ember' in 'prod').
    """

    id: NodeID | None = None
    agent: str = Field(
        ...,
        description="The agent this profile applies to (e.g., 'Ember', 'Unity').",
    )
    name: str = Field(..., description="The context name (e.g., 'prod', 'dev', 'safety_review').")
    version: str = Field(..., description="Version of this profile binding.")
    facet_ids: list[NodeID] = Field([], description="List of active facet IDs for this profile.")
    rule_ids: list[NodeID] = Field([], description="List of active rule IDs for this profile.")


class ComposeRequest(BaseModel):
    """
    Request to compose a prompt patch for a given agent and context.
    """

    agent: str = Field(..., description="The agent requesting the identity patch.")
    profile_name: str = Field("default", description="The profile to use (e.g., 'prod', 'dev').")
    episode_id: str | None = Field(None, description="Synapse episode ID for audit and replay.")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for composition policy selection.",
    )
    intent: str | None = None          # ← optional
    task_key: str | None = None        # ← optional
    budget_tokens: int = Field(4096, description="The maximum token budget for the composed patch.")


class ComposeResponse(BaseModel):
    """
    A deterministically generated prompt patch with full citation of its sources.
    """

    episode_id: str
    prompt_patch_id: NodeID = Field(
        ...,
        description="The ID of the persisted PromptPatch node in Neo4j.",
    )
    checksum: str = Field(..., description="SHA256 hash of the generated text for verification.")
    included_facets: list[NodeID] = Field(
        ...,
        description="List of facet IDs used in the composition.",
    )
    included_rules: list[NodeID] = Field(
        ...,
        description="List of rule IDs used in the composition.",
    )
    rcu_ref: str = Field(..., description="Reference to the RCU snapshot for this composition.")
    text: str = Field(..., description="The fully composed, deterministic prompt patch text.")
    warnings: list[str] = Field([], description="Any non-fatal warnings, e.g., near-budget limits.")


# --- NEW FOR H1 ---


class Attestation(BaseModel):
    run_id: str
    episode_id: str
    agent: str
    applied_prompt_patch_id: str
    coverage: float | None = Field(None, ge=0, le=1)
    breaches: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}  # pydantic v2



class DriftReport(BaseModel):
    """
    A data structure summarizing identity drift and rule adherence over a
    specific time window. Generated by the HomeostasisMonitor.
    """

    agent: str
    window: str  # e.g., "last_100_outputs"
    style_delta: float
    content_delta: float
    rule_breach_count: int
    uncertainty: float
    details: dict[str, Any] = Field(default_factory=dict)

    # APPEND THIS CLASS TO systems/equor/schemas.py


class PatchProposalEvent(BaseModel):
    """
    The event payload published when the HomeostasisMonitor proposes a
    corrective action in response to detected drift.
    """

    proposal_id: str = Field(..., description="A unique ID for this proposal.")
    agent: str = Field(..., description="The agent for whom the patch is proposed.")
    triggering_report: DriftReport = Field(
        ...,
        description="The drift report that triggered this proposal.",
    )
    proposed_patch_text: str = Field(
        ...,
        description="The full text of the new, 'tightened' PromptPatch.",
    )
    notes: str = Field(..., description="Explanation of why the patch was proposed.")

    # APPEND THESE CLASSES TO systems/equor/schemas.py


class Invariant(BaseModel):
    """
    Defines a high-level invariant that must hold true across the system.
    """

    id: str = Field(..., description="A unique ID for the invariant, e.g., 'safety_over_style'.")
    description: str = Field(
        ...,
        description="A human-readable description of what the invariant checks.",
    )
    cypher_query: str = Field(
        ...,
        description="A Cypher query that returns violations. An empty result means the invariant holds.",
    )


class InvariantCheckResult(BaseModel):
    """
    The result of running an invariant check.
    """

    invariant_id: str
    holds: bool
    violations_found: int
    details: list[dict[str, Any]] = Field(
        default_factory=list,
        description="A list of nodes or relationships that violate the invariant.",
    )

    # APPEND THESE CLASSES TO systems/equor/schemas.py


class InternalStateMetrics(BaseModel):
    """
    A raw snapshot of key internal performance and dissonance metrics
    captured during a single cognitive operation (e.g., a prompt composition).
    """

    cognitive_load: float = Field(..., description="Time taken for the operation in ms.")
    dissonance_score: float = Field(
        ...,
        description="A measure of internal conflict, e.g., number of high-priority rules evaluated.",
    )
    integrity_score: float = Field(
        ...,
        description="A measure of constitutional adherence, e.g., attestation coverage.",
    )
    curiosity_score: float = Field(
        ...,
        description="A measure of novelty, e.g., OOD distance from Synapse.",
    )
    episode_id: str


class QualiaState(BaseModel):
    """
    Represents a single point of subjective experience, logged to the graph.
    It contains the compressed representation of the internal state.
    """

    id: str
    timestamp: str
    manifold_coordinates: list[float] = Field(
        ...,
        description="The low-dimensional vector representing the subjective state.",
    )
    triggering_episode_id: str
