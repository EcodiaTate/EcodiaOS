# systems/axon/learning/feedback.py
from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.axon.schemas import ActionResult, AxonIntent

# ----------------- Models -----------------


class UpliftReport(BaseModel):
    """
    A detailed report comparing a predicted result with an actual result.
    This serves as a rich learning signal for Synapse.
    """

    intent: AxonIntent
    status_change: str | None  # e.g., "ok -> fail"
    output_diff: dict[str, Any]
    # Optional context for learning
    predicted_metrics: dict[str, Any] | None = None
    actual_metrics: dict[str, Any] | None = None


# ----------------- Helpers -----------------


def _calculate_diff(
    d1: dict[str, Any] | None, d2: dict[str, Any] | None, path: str = ""
) -> dict[str, Any]:
    """Recursively diffs two dictionaries."""
    d1 = d1 or {}
    d2 = d2 or {}
    diff: dict[str, Any] = {}

    for k in d1:
        p = f"{path}.{k}" if path else k
        if k not in d2:
            diff[p] = {"removed": d1[k]}
        elif isinstance(d1[k], dict) and isinstance(d2[k], dict):
            sub_diff = _calculate_diff(d1[k], d2[k], path=p)
            if sub_diff:
                diff.update(sub_diff)
        elif d1[k] != d2[k]:
            diff[p] = {"changed": {"from": d1[k], "to": d2[k]}}
    for k in d2:
        p = f"{path}.{k}" if path else k
        if k not in d1:
            diff[p] = {"added": d2[k]}
    return diff


async def _post_json(path: str, body: dict[str, Any], *, decision_id: str | None = None) -> None:
    headers = {"x-budget-ms": os.getenv("AXON_FEEDBACK_BUDGET_MS", "800")}
    if decision_id:
        headers["x-decision-id"] = decision_id
    client = await get_http_client()
    await client.post(path, json=body, headers=headers)


def _ingest_endpoint() -> str:
    # Canonical endpoint name; safe fallback for dev
    return getattr(ENDPOINTS, "SYNAPSE_INGEST_OUTCOME", None) or "/synapse/ingest_outcome"


# ----------------- Public API -----------------


async def ingest_action_outcome(
    intent: AxonIntent,
    predicted_result: ActionResult,
    actual_result: ActionResult,
    *,
    decision_id: str | None = None,
) -> None:
    """
    Calculates a detailed uplift report and sends it to Synapse via SYNAPSE_INGEST_OUTCOME.
    """
    status_change = None
    if predicted_result.status != actual_result.status:
        status_change = f"{predicted_result.status} -> {actual_result.status}"

    output_diff = _calculate_diff(predicted_result.outputs, actual_result.outputs)

    report = UpliftReport(
        intent=intent,
        status_change=status_change,
        output_diff=output_diff,
        predicted_metrics=predicted_result.counterfactual_metrics or {},
        actual_metrics=actual_result.counterfactual_metrics or {},
    )

    try:
        await _post_json(_ingest_endpoint(), report.model_dump(), decision_id=decision_id)
        # Optional: print for local dev visibility (quiet in prod)
        if os.getenv("AXON_DEBUG", "0") == "1":
            print(f"[Feedback] Ingested uplift report for intent {intent.intent_id}")
    except Exception as e:
        if os.getenv("AXON_DEBUG", "0") == "1":
            print(f"[Feedback] ingest_action_outcome failed: {e}")


async def log_outcome_to_synapse(
    payload: dict[str, Any], *, decision_id: str | None = None
) -> None:
    """
    General-purpose logger to SYNAPSE_INGEST_OUTCOME for arbitrary
    learning payloads (A/B summaries, rollout decisions, etc.).
    """
    try:
        await _post_json(_ingest_endpoint(), payload, decision_id=decision_id)
    except Exception as e:
        if os.getenv("AXON_DEBUG", "0") == "1":
            print(f"[Feedback] log_outcome_to_synapse failed: {e}")
