# systems/simula/memory/schemas.py

from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, Field


class SynapticTrace(BaseModel):
    """
    Represents a learned, reflexive memory. It maps a specific problem
    signature (the trigger) to a proven sequence of actions (the reflex).
    """

    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex}")

    # The multi-modal "smell" of a problem
    triggering_state_vector: list[float]

    # The exact, successful sequence of tool calls that solved the problem
    action_sequence: list[dict[str, Any]]

    # The utility score from the run that created this trace
    outcome_utility: float

    # The bandit-managed confidence score (how reliable is this reflex?)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # Metadata for analysis
    generation_timestamp: float
    last_applied_timestamp: float | None = None
    application_count: int = 0
