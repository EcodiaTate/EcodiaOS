# core/prompting/spec.py
# --- FINAL VERSION WITH ORCHESTRATOR WORKFLOW SCHEMAS (FULL & CORRECTED) ---
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ──────────────────────────────────────────────────────────────────────────────
# Enums / literals
# ──────────────────────────────────────────────────────────────────────────────

ParseMode = Literal["strict_json", "tolerant", "auto_repair"]

# +++ FIX: Add all new and existing lenses to this Literal list.
# This is the master list that Pydantic uses to validate the `context_lenses`
# field in all of your PromptSpec YAML files.
LensName = Literal[
    # Original Lenses
    "equor.identity",
    "atune.salience",
    "affect",
    "retrieval.semantic",
    "event.canonical",
    "tools.catalog",
    "lens_get_tools",
    "lens_simula_advice_preplan",
    "lens_simula_advice_postplan",
    "ecodia.self_concept",
    # Added New Facet Lenses
    "facets.affective",
    "facets.ethical",
    "facets.philosophical",
    "facets.safety",
    "facets.style",
    "facets.voice",
    "facets.mission",
    "facets.operational",
    "facets.compliance",
    "facets.epistemic_humility",
]

# ──────────────────────────────────────────────────────────────────────────────
# PromptSpec Models
# ──────────────────────────────────────────────────────────────────────────────


class ProviderOverrides(BaseModel):
    """Defines the final, resolved provider settings for an LLM call."""

    max_tokens: int
    temperature: float | None = None
    json_mode: bool = True


class Outputs(BaseModel):
    """Defines the expected output constraints for a prompt spec."""

    model_config = ConfigDict(populate_by_name=True)

    schema_ref: str | None = Field(default=None, description="Path/URL to a JSON Schema file.")
    schema_: dict[str, Any] | None = Field(
        default=None,
        alias="schema",
        description="Direct JSON Schema object.",
    )
    parse_mode: ParseMode = "strict_json"

    @model_validator(mode="after")
    def _check_schema_source(self) -> Outputs:
        if self.schema_ref and self.schema_ is not None:
            raise ValueError("Provide 'schema_ref' or 'schema', but not both.")
        return self


class BudgetPolicy(BaseModel):
    tokens_key: str = "tokens"
    ms_key: str = "ms"
    max_tokens_fallback: int = 800


class IdentityBlock(BaseModel):
    agent: str
    persona_partial: str | None = None


class SafetySpec(BaseModel):
    partials: list[str] = Field(default_factory=list)


class PromptSpec(BaseModel):
    id: str
    version: str
    scope: str
    identity: IdentityBlock
    safety: SafetySpec = Field(default_factory=SafetySpec)
    outputs: Outputs = Field(default_factory=Outputs)
    budget_policy: BudgetPolicy = Field(default_factory=BudgetPolicy)
    context_lenses: list[LensName] = Field(default_factory=list)
    partials: list[str] = Field(default_factory=list)
    ablation_knobs: dict[str, list[Any]] = Field(default_factory=dict)
    template: str | None = Field(default=None)
    context_vars: dict[str, str] = Field(default_factory=dict)

    @field_validator("id", "scope")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("must not be empty")
        return v


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator Workflow Schemas (Moved here to prevent circular imports)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class OrchestratorResponse:
    """The structured output from building a prompt, ready for an LLM gateway."""

    messages: list[dict[str, str]]
    provider_overrides: dict[str, Any]
    provenance: dict[str, Any]
