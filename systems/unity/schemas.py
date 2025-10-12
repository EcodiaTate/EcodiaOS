from typing import Any, Literal

from pydantic import BaseModel, Field

# A unique identifier for a node in the Neo4j graph.
NodeID = str


class InputRef(BaseModel):
    """A reference to an input artifact for the deliberation."""

    kind: Literal["text", "doc", "code", "graph_ref", "url", "artifact_ref", "json"]
    value: str
    meta: dict[str, Any] = Field(default_factory=dict)


class DeliberationSpec(BaseModel):
    """
    The specification for a new deliberation session. This is the primary
    input to the /deliberate endpoint.
    """

    triggering_event_id: str | None = Field(
        None, description="The ID of the event from Atune that triggered this deliberation."
    )
    topic: str = Field(..., description="A concise, human-readable topic for the deliberation.")
    goal: Literal[
        "assess",
        "select",
        "approve_patch",
        "risk_review",
        "policy_review",
        "design_review",
    ] = Field(..., description="The high-level goal of the deliberation.")
    inputs: list[InputRef] = Field(
        default_factory=list,
        description="A list of inputs to be considered.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Constitutional rule IDs or text constraints.",
    )
    protocol_hint: str | None = Field(
        None,
        description="A hint to Synapse for protocol selection.",
    )
    episode_id: str | None = Field(None, description="Synapse episode ID for audit and replay.")
    urgency: Literal["low", "normal", "high"] = "normal"
    require_artifacts: list[
        Literal["argument_map", "transcript", "verdict", "dissent", "rcu_snapshot"]
    ] = ["verdict"]


class VerdictModel(BaseModel):
    """
    The structured output of a deliberation, representing the final decision.
    """

    outcome: Literal["APPROVE", "REJECT", "NEEDS_WORK", "NO_ACTION"]
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="The calculated confidence in the outcome [0,1].",
    )
    uncertainty: float = Field(
        ...,
        ge=0,
        le=1,
        description="The calculated uncertainty or ambiguity [0,1].",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="For APPROVE verdicts, a list of binding constraints.",
    )
    dissent: str | None = Field(
        None,
        description="A summary of the dissenting opinions, if any.",
    )
    followups: list[str] = Field(
        default_factory=list,
        description="Actionable follow-up tasks required.",
    )
    constitution_refs: list[str] = Field(
        default_factory=list,
        description="Equor rule IDs cited in the verdict.",
    )


class DeliberationResponse(BaseModel):
    """
    The final response from the /deliberate endpoint, containing the verdict
    and references to all generated artifacts.
    """

    episode_id: str
    deliberation_id: NodeID
    verdict: VerdictModel
    artifact_ids: dict[str, NodeID] = Field(
        ...,
        description="Mapping of artifact types to their Neo4j node IDs.",
    )


class MetaCriticismProposalEvent(BaseModel):
    """
    The event payload published when Unity's meta-criticism protocol
    proposes a task for Synapse to improve deliberation strategies.
    """

    proposal_id: str = Field(..., description="A unique ID for this proposal.")
    source_deliberation_id: str = Field(
        ...,
        description="The ID of the deliberation that was analyzed.",
    )
    proposed_task_goal: str = Field(..., description="The suggested goal for a new Synapse task.")
    evidence: dict[str, Any] = Field(
        ...,
        description="Data from the source deliberation to justify the proposal.",
    )
    notes: str = Field(..., description="A human-readable explanation of the proposed improvement.")


class RoomConfiguration(BaseModel):
    """Defines the configuration for a single room in a federated deliberation."""

    protocol_id: str
    panel: list[str]
    # Other hyper-parameters could be added here


class FederatedConsensusRequest(BaseModel):
    """The request to start a high-stakes, multi-room federated consensus deliberation."""

    base_spec: DeliberationSpec = Field(
        ...,
        description="The base deliberation spec for all rooms.",
    )
    room_configs: list[RoomConfiguration] = Field(
        ...,
        description="A list of diverse configurations for the parallel rooms.",
    )
    quorum_threshold: float = Field(
        0.75,
        ge=0,
        le=1,
        description="The percentage of 'APPROVE' verdicts required for a final approval.",
    )


class FederatedConsensusResponse(BaseModel):
    """The final aggregated verdict from a federated consensus deliberation."""

    meta_verdict: VerdictModel
    room_verdicts: list[VerdictModel] = Field(
        ...,
        description="A list of the individual verdicts from each room.",
    )


class Cognit(BaseModel):
    """
    A discrete piece of information or insight generated by a sub-process,
    intended for the Global Workspace.
    """

    id: str
    source_process: str  # e.g., "SafetyCritic"
    content: str
    salience: float = Field(
        ...,
        ge=0,
        le=1,
        description="The sub-process's own estimate of how important this information is.",
    )
    timestamp: str


class BroadcastEvent(BaseModel):
    """
    The event payload for a workspace "ignition", when a cognit is selected
    and broadcast to all active sub-processes.
    """

    broadcast_id: str
    selected_cognit: Cognit
    notes: str
