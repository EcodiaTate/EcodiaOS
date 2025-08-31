# systems/synapse/skills/schemas.py
# NEW FILE
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Option(BaseModel):
    """
    Represents a reusable macro-policy or "skill" discovered from experience. (H13)
    """

    id: str = Field(..., description="Unique identifier for this option.")
    initiation_set: list[dict[str, Any]] = Field(
        ...,
        description="A cluster of contexts where this option is applicable.",
    )
    termination_condition: dict[str, Any] = Field(
        ...,
        description="A state that signals the successful completion of the option.",
    )
    policy_sequence: list[str] = Field(
        ...,
        description="An ordered list of policy arm IDs that constitute the option.",
    )
    expected_reward: float = Field(
        ...,
        description="The average reward achieved when this option completes successfully.",
    )
    discovery_trace: str = Field(
        ...,
        description="The episode ID chain from which this option was mined.",
    )
