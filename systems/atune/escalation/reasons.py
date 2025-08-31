# systems/atune/escalation/reasons.py
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Kind = Literal["conformal_ood", "postcond_violation", "rollback_failed", "twin_mismatch"]


class EscalationReason(BaseModel):
    kind: Kind = Field(..., description="Structured cause for escalation.")
    detail: dict[str, Any] = Field(default_factory=dict)


def reason_conformal_ood(pvals: dict[str, float], alpha: float) -> EscalationReason:
    return EscalationReason(kind="conformal_ood", detail={"pvals": pvals, "alpha": alpha})


def reason_postcond_violation(violations: Any) -> EscalationReason:
    return EscalationReason(kind="postcond_violation", detail={"violations": violations})


def reason_rollback_failed(error: str) -> EscalationReason:
    return EscalationReason(kind="rollback_failed", detail={"error": error})


def reason_twin_mismatch(residual: float) -> EscalationReason:
    return EscalationReason(kind="twin_mismatch", detail={"residual": residual})
