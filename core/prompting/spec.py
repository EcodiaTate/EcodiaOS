# core/prompting/spec.py
# --- PROJECT SENTINEL UPGRADE (Corrected) ---
from __future__ import annotations

from typing import Any, Literal

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

LensName = Literal[
    "equor.identity",
    "atune.salience",
    "affect",
    "retrieval.semantic",
    "event.canonical",
]

# ──────────────────────────────────────────────────────────────────────────────
# Models
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

    @field_validator("id", "scope")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("must not be empty")
        return v
