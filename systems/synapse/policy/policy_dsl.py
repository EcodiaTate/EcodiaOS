# systems/synapse/policy/policy_dsl.py
# COMPLETE, CORRECTED, AND FINAL VERSION

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Literal, Set, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

# --- Effect Definitions ---
# These models define the specific, machine-readable instructions a policy can contain.


class LLMParamsEffect(BaseModel):
    type: Literal["llm_params"] = "llm_params"
    model: str
    temperature: float
    max_tokens: int


class ToolBiasEffect(BaseModel):
    type: Literal["tool_bias"] = "tool_bias"
    # Maps tool_name (e.g., "google_pse") to a multiplicative weight.
    # > 1.0 encourages use, < 1.0 discourages.
    weights: dict[str, float]


class TagBiasEffect(BaseModel):
    type: Literal["tag_bias"] = "tag_bias"
    # A set of tags that this policy is designed for.
    # The selector can use this for more precise filtering.
    tags: list[str]


class StyleInjectionEffect(BaseModel):
    """An effect to inject a dictionary of style parameters into the prompt context."""

    type: Literal["style_injection"] = "style_injection"
    style_dict: dict[str, Any] = Field(
        ...,
        description="The dictionary to be merged into the rendering context.",
    )


# A discriminated union of all possible effect types.
PolicyEffect = Union[LLMParamsEffect, ToolBiasEffect, TagBiasEffect, StyleInjectionEffect]


# Pydantic's RootModel allows the list of union types to be validated correctly.
class PolicyEffectList(RootModel[list[PolicyEffect]]):
    root: list[PolicyEffect]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]


# --- Core Policy Graph ---


# Base model for Pydantic v1/v2 compatibility
class _BaseModel(BaseModel):
    if hasattr(ConfigDict, "model_config"):  # Pydantic v2
        model_config = ConfigDict(extra="ignore", populate_by_name=True)
    else:  # Pydantic v1

        class Config:
            extra = "ignore"
            validate_by_name = True


class PolicyNode(_BaseModel):
    """A single node in a policy graph, like a prompt or a tool call."""

    id: str = Field(..., description="Unique identifier for the node within the graph.")
    type: Literal["prompt", "tool", "guard", "subgraph"]
    # We keep model/params here for legacy compatibility or simple arms,
    # but they will be superseded by the LLMParamsEffect for learned arms.
    model: str | None = Field(None, description="For 'prompt' nodes, the LLM to use.")
    params: dict[str, Any] = Field(default_factory=dict)
    effects: list[str] = Field(
        default_factory=list,
        description="Legacy side-effects field (e.g., ['read', 'write']).",
    )


class PolicyGraph(_BaseModel):
    """
    Represents a policy as a structured program. This version is upgraded with an
    explicit, machine-readable `effects` list that dictates its behavior.
    """

    id: str | None = Field(default=None)
    version: int = 2  # Version 2 of the schema includes the rich effects list
    nodes: list[PolicyNode] = Field(default_factory=list)
    effects: PolicyEffectList = Field(
        default_factory=lambda: PolicyEffectList(root=[]),
        description="A list of structured effects that define the policy's behavior.",
    )

    @property
    def canonical_hash(self) -> str:
        """Computes a stable hash for deduplication."""
        # model_dump_json is used to correctly serialize the Union type in the effects list.
        canonical_json = self.model_dump_json(sort_keys=True, exclude_none=True)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def _validate_graph_integrity(self) -> PolicyGraph:
        """Ensures node IDs are unique within the graph."""
        seen: set[str] = set()
        for n in self.nodes:
            if n.id in seen:
                raise ValueError(f"Duplicate node id in PolicyGraph: '{n.id}'")
            seen.add(n.id)
        return self
