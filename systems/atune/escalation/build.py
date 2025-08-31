# systems/atune/escalation/build.py
from __future__ import annotations

from typing import Any

from systems.atune.escalation.reasons import EscalationReason


def build_escalation_payload(
    *,
    episode_id: str,
    reason: EscalationReason,
    decision_id: str,
    event_id: str | None = None,
    intent: dict[str, Any] | None = None,
    predicted_result: dict[str, Any] | None = None,
    predicted_utility: float | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "episode_id": episode_id,
        "reason": reason.model_dump(),
        "intent": intent,
        "predicted_result": predicted_result,
        "predicted_utility": predicted_utility,
        "context": {
            "decision_id": decision_id,
            **({"event_id": event_id} if event_id else {}),
            **(context or {}),
        },
        "rollback_options": {},
    }
