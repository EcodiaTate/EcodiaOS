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
    """
    Constructs the standard payload for an escalation request to the bridge.

    Args:
        episode_id: The Synapse or planner episode ID.
        reason: The structured reason for the escalation.
        decision_id: The overarching decision ID for the cognitive cycle.
        event_id: The specific event ID that triggered the escalation.
        intent: An optional, pre-formed intent object. If not provided, one will
                be created using the event_id or decision_id.
        predicted_result: Optional predicted outcome from a simulation.
        predicted_utility: Optional predicted utility score.
        context: Additional key-value pairs for context.

    Returns:
        A dictionary formatted for the /escalate endpoint.
    """
    final_intent = intent

    # FIX: The `intent` field is mandatory for the receiving endpoint.
    # If a full intent object isn't provided, we construct the required
    # {"intent_id": "..."} structure using the most relevant available ID.
    if final_intent is None:
        # Prioritize the specific event_id if it exists, otherwise use the
        # cycle's decision_id as a fallback identifier.
        intent_id_source = event_id if event_id is not None else decision_id
        final_intent = {"intent_id": intent_id_source}

    return {
        "episode_id": episode_id,
        "reason": reason.model_dump(),
        "intent": final_intent,
        "predicted_result": predicted_result,
        "predicted_utility": predicted_utility,
        "context": {
            "decision_id": decision_id,
            **({"event_id": event_id} if event_id else {}),
            **(context or {}),
        },
        "rollback_options": {},
    }
