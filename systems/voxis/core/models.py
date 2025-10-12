# systems/voxis/core/models.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class VoxisTalkRequest(BaseModel):
    """
    Defines the contract for an incoming request to the /talk endpoint.
    This is the data received directly from the frontend client.
    """

    user_input: str = Field(..., description="The raw text input from the user.")
    user_id: str = Field(..., description="The unique identifier for the user.")

    # Frontend sends soul_event_id; we treat it as session_id internally.
    session_id: str = Field(
        ...,
        alias="soul_event_id",
        description="The session identifier, used to retrieve the user's SoulNode.",
    )

    output_mode: str = Field(
        default="typing",
        description="The client's desired output mode: 'voice' or 'typing'.",
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class TaskContext(BaseModel):
    """
    The rich context bundle assembled by the VoxisPipeline. This is the complete
    worldview that will be passed to Synapse to make an informed decision.
    """

    # Core request data
    user_input: str
    user_id: str
    session_id: str
    output_mode: str

    # Enriched data fetched from other EOS organs
    soul_node: str | None = Field(
        None,
        description="The decrypted personal context string for the user session.",
    )
    conversation_history: list[dict[str, str]] | None = Field(
        None,
        description="Recent turns of the conversation.",
    )
    user_profile: dict[str, Any] | None = Field(
        None,
        description="User preferences and long-term data from Qora.",
    )
    world_state: dict[str, Any] | None = Field(
        None,
        description="Real-time sensor and state data from Axon.",
    )
    constitution: dict[str, Any] | None = Field(
        None,
        description="The active set of rules and principles from Equor.",
    )

    model_config = ConfigDict(extra="allow")


class EosAction(BaseModel):
    """
    Represents a single, discrete action step within a plan returned by Synapse.
    This structure allows for complex, multi-step agentic behavior.
    """

    action_type: str = Field(..., description="e.g., 'tool_call' or 'respond'.")
    tool_name: str | None = Field(
        None,
        description="Tool to execute if action_type is 'tool_call'.",
    )
    parameters: dict[str, Any] | None = Field(
        None,
        description="Arguments for the tool call.",
    )

    model_config = ConfigDict(extra="allow")


class EosPlan(BaseModel):
    """
    Defines the complete, structured plan of action returned by Synapse.
    This is the authoritative decision that Voxis must execute.

    Extended to carry optional style/metadata so the synthesizer can modulate tone
    and we can persist upserts/bandit diagnostics without losing fields.
    """

    episode_id: str = Field(
        ...,
        description="Unique ID for this decision episode, used for logging/feedback.",
    )
    champion_arm_id: str = Field(
        ...,
        description="Policy arm ID chosen by Synapse (e.g., dyn::<hash>).",
    )

    # Planner outputs
    scratchpad: str | None = Field(
        None,
        description="Chain-of-thought style reasoning from the planner LLM.",
    )
    plan: list[EosAction] = Field(
        ...,
        description="Sequence of actions to be executed by the pipeline.",
    )
    final_synthesis_prompt: str | None = Field(
        None,
        description="Final instruction to the LLM for generating the user-facing response.",
    )
    interim_thought: str = Field(
        ...,
        description="A brief, user-facing sentence indicating what the agent is about to do. Sent to the client immediately.",
    )
    # NEW: style & meta for style-aware synthesis and observability
    style: dict[str, Any] | None = Field(
        default=None,
        description="Tone/style hints (e.g., {'tone':'playful','pacing':'brisk','formality':'low'}).",
    )
    policy_graph_meta: dict[str, Any] | None = Field(
        default=None,
        description="Hints extracted from a policy graph; may include 'style'.",
    )
    bandit_meta: dict[str, Any] | None = Field(
        default=None,
        description="Diagnostics (features hash, ucb terms, etc.).",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Arbitrary plan-level metadata.",
    )

    # NEW: pass-through of profile upserts from the planner (if any)
    profile_upserts: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Optional suggested SoulProfile updates from the planner. "
            "Each item typically includes label, merge_key, merge_value, updates, confidence."
        ),
    )

    model_config = ConfigDict(extra="allow")
