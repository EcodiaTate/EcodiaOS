# systems/synapse/policy/policy_dsl.py
# NEW FILE FOR PHASE II
from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, Field

# This module implements the Policy=Program DSL from vision doc B3

EffectType = Literal["read", "write", "net_access", "execute", "state_change"]
ConstraintClass = Literal["normal", "danger"]


class PolicyNode(BaseModel):
    """A single node in a policy graph, like a prompt or a tool call."""

    id: str = Field(..., description="Unique identifier for the node within the graph.")
    type: Literal["prompt", "tool", "guard", "subgraph"]
    model: str | None = Field(None, description="For 'prompt' nodes, the LLM to use.")
    params: dict[str, Any] = Field(default_factory=dict)
    effects: list[EffectType] = Field(
        default_factory=list,
        description="The inferred side-effects of this node.",
    )


class PolicyEdge(BaseModel):
    """A directed edge connecting two nodes in the policy graph."""

    source: str = Field(..., description="The ID of the source node.")
    target: str = Field(..., description="The ID of the target node.")


class PolicyConstraint(BaseModel):
    """A formal constraint applied to the policy graph, potentially verifiable by SMT."""

    constraint_class: ConstraintClass = Field("normal", alias="class")
    smt_expression: str | None = Field(
        None,
        alias="smt",
        description="A Z3-compatible SMT expression.",
    )


class PolicyGraph(BaseModel):
    """
    Represents a policy as a structured program (a directed graph).
    This allows for static analysis, effect typing, and formal verification.
    """

    version: int = 1
    nodes: list[PolicyNode]
    edges: list[PolicyEdge]
    constraints: list[PolicyConstraint] = Field(default_factory=list)

    @property
    def canonical_hash(self) -> str:
        """Computes a stable hash for deduplication, as per vision C7."""
        # Use Pydantic's json() method with sorted keys for a canonical representation
        canonical_json = self.model_dump_json(sort_keys=True, exclude_none=True)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
