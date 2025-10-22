from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Kind = Literal[
    "conformal_ood",
    "postcond_violation",
    "rollback_failed",
    "twin_mismatch",
    "planner_decision",
]


class EscalationReason(BaseModel):
    kind: Kind = Field(..., description="Structured cause for escalation.")
    detail: dict[str, Any] = Field(default_factory=dict)


def reason_conformal_ood(pvals: dict[str, float], alpha: float) -> EscalationReason:
    # FIX: Explicitly cast values to standard Python floats to prevent JSON
    # serialization errors downstream if numpy floats are passed in.
    sanitized_pvals = {k: float(v) for k, v in pvals.items()}
    return EscalationReason(
        kind="conformal_ood",
        detail={"pvals": sanitized_pvals, "alpha": float(alpha)},
    )


def reason_postcond_violation(violations: Any) -> EscalationReason:
    return EscalationReason(kind="postcond_violation", detail={"violations": violations})


def reason_rollback_failed(error: str) -> EscalationReason:
    return EscalationReason(kind="rollback_failed", detail={"error": error})


def reason_twin_mismatch(residual: float) -> EscalationReason:
    return EscalationReason(kind="twin_mismatch", detail={"residual": float(residual)})


def reason_planner_decision(salience_scores: dict[str, float], reason: str) -> EscalationReason:
    """
    Use this when the planner explicitly decides an event needs Unity.
    """
    # FIX: Explicitly cast values to standard Python floats. This handles cases
    # where the salience scores are numpy.float32/64, which are not serializable
    # by the standard json library used in the bridge service.
    sanitized_scores = {k: float(v) for k, v in salience_scores.items()}
    return EscalationReason(
        kind="planner_decision",
        detail={"salience_scores": sanitized_scores, "reason": reason},
    )
