from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# Axon contract atoms: {path, op, value}
class ContractAtom(BaseModel):
    path: str = Field(..., description="JSONPath-like (dot) path, e.g. 'result.status'")
    op: Literal["exists", "equals", "lt", "lte", "gt", "gte", "contains"] = "exists"
    value: Any | None = None


class RateLimits(BaseModel):
    rps: float | None = None
    burst: int | None = None


class Redactions(BaseModel):
    fields: list[str] = Field(default_factory=list)
    patterns: dict[str, str] = Field(default_factory=dict)  # name -> regex


class SafetyBlock(BaseModel):
    pii_guard: bool = False
    domain_allowlist: list[str] = Field(default_factory=list)
    domain_blocklist: list[str] = Field(default_factory=list)


class Playbook(BaseModel):
    capability: str | None = None
    rate_limits: RateLimits | None = None
    redactions: Redactions | None = None
    preconditions: list[ContractAtom] = Field(default_factory=list)
    postconditions: list[ContractAtom] = Field(default_factory=list)
    safety: SafetyBlock | None = None
    capability_spec: dict[str, Any] = Field(default_factory=dict)
    recommendation: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

    @field_validator("preconditions", "postconditions")
    @classmethod
    def _coerce_atoms(cls, values: list[ContractAtom]) -> list[ContractAtom]:
        """
        Validator to process the entire list of atoms.
        In Pydantic V2, `each_item=True` is removed. Instead, the validator
        receives the whole list, and we iterate through it.
        """
        validated_atoms = []
        for v in values:
            # Ensure value presence matches op semantics
            if v.op == "exists":
                # Create a new, corrected instance, ensuring value is None
                validated_atoms.append(ContractAtom(path=v.path, op=v.op, value=None))
            else:
                validated_atoms.append(v)
        return validated_atoms


def normalize_playbook(raw: dict[str, Any]) -> Playbook:
    """
    Accepts any dict; returns a typed Playbook with defaults applied.
    Never throws—falls back to permissive fields where needed.
    """
    try:
        return Playbook(**(raw or {}))
    except Exception:
        # Best-effort permissive construct
        return Playbook()
