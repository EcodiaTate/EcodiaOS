# core/prompting/spec.py
# --- FINAL VERSION WITH ORCHESTRATOR WORKFLOW SCHEMAS (FULL & CORRECTED) ---
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

import yaml
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
# This is the master list Pydantic uses to validate `context_lenses`
# in all PromptSpec YAML files.
LensName = Literal[
    # Legacy/other lenses (kept for forward-compat; no-ops if not present)
    "equor.identity",
    "atune.salience",
    "affect",
    "retrieval.semantic",
    "event.canonical",
    "tools.catalog",
    "ecodia.self_concept",
    # Simula lenses (actively used)
    "lens_get_tools",
    "lens_simula_advice_preplan",
    # (reserved, not currently used)
    "lens_simula_advice_postplan",
    # Facets (safe to ignore if not wired)
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
# Orchestrator Workflow Schemas (kept here to prevent circular imports)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class OrchestratorResponse:
    """Structured output from building a prompt, ready for the gateway."""

    messages: list[dict[str, str]]
    provider_overrides: dict[str, Any]
    provenance: dict[str, Any]


# ──────────────────────────────────────────────────────────────────────────────
# Spec loading / registry
# ──────────────────────────────────────────────────────────────────────────────

_SPEC_CACHE: dict[str, dict[str, Any]] = {}

SUPPORTED_PARSE_MODES = {"strict_json", "auto_repair", "tolerant"}

# NOTE: simula.main.planning is deprecated and intentionally excluded.
DEFAULT_SPEC_PATHS = [
    "core/prompting/promptspecs/simula_deliberation_planner.v1.yaml",
    "core/prompting/promptspecs/simula_deliberation_red_team.v1.yaml",
    "core/prompting/promptspecs/simula_deliberation_judge.v1.yaml",
    "core/prompting/promptspecs/simula_utility_scorer.v1.yaml",
]


def _load_yaml_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
        # Support either a single doc that is a list, or multi-doc
        if len(docs) == 1 and isinstance(docs[0], list):
            return docs[0]
        # Flatten multi-doc streams into a list of dicts
        out: list[dict] = []
        for d in docs:
            if isinstance(d, list):
                out.extend(d)
            elif isinstance(d, dict):
                out.append(d)
        return out


def _validate_spec_dict(sp: dict) -> None:
    # Required top-level keys in your YAMLs
    for key in ("id", "version", "scope", "identity", "partials", "outputs"):
        if key not in sp:
            raise ValueError(f"PromptSpec missing required key: {key} (id={sp.get('id')})")

    # identity
    ident = sp.get("identity") or {}
    if "agent" not in ident:
        raise ValueError(f"PromptSpec.identity.agent missing (id={sp['id']})")

    # parse_mode sanity
    pmode = (sp.get("outputs", {}).get("parse_mode") or "strict_json").strip()
    if pmode not in SUPPORTED_PARSE_MODES:
        raise ValueError(f"Unsupported parse_mode '{pmode}' in spec id={sp['id']}")

    # optional schema (planner/red-team/judge have schemas; scorer is tolerant)
    # we don't force presence; gateway handles tolerant/auto_repair parsing.


def preload_prompt_specs(paths: list[str] | None = None) -> None:
    """Call once at process boot (idempotent)."""
    _SPEC_CACHE.clear()
    for p in paths or DEFAULT_SPEC_PATHS:
        if not os.path.exists(p):
            continue
        try:
            for sp in _load_yaml_file(p):
                _validate_spec_dict(sp)
                # We store raw dicts because the builder expects dict access;
                # If you want Pydantic instances, validate with PromptSpec(**sp)
                _SPEC_CACHE[sp["scope"]] = sp
        except Exception as e:
            # Fail fast but keep the error clear on which file was bad.
            raise RuntimeError(f"Failed loading spec file '{p}': {e}") from e


def get_spec_by_scope(scope: str) -> dict:
    """Return the raw spec dict for a given scope (build_prompt expects dict)."""
    if not _SPEC_CACHE:
        preload_prompt_specs()
    sp = _SPEC_CACHE.get(scope)
    if not sp:
        raise KeyError(f"No PromptSpec registered for scope='{scope}'")
    return sp


def list_specs() -> list[str]:
    if not _SPEC_CACHE:
        preload_prompt_specs()
    return sorted(_SPEC_CACHE.keys())
