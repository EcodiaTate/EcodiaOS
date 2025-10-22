from __future__ import annotations

import json
from typing import Any

import httpx  # Import httpx to catch specific network/HTTP errors
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.atune.escalation.reasons import EscalationReason
from systems.unity.schemas import DeliberationSpec, InputRef


# --- Pydantic models for the incoming payload are well-defined and kept as is ---
class AtuneEscalateIntent(BaseModel):
    intent_id: str


class AtuneEscalateRollbackOptions(BaseModel):
    constraints: list[str] = Field(default_factory=list)


class AtuneEscalateRequest(BaseModel):
    """Defines the structure of the incoming request from other internal systems."""

    reason: str | EscalationReason | dict[str, Any] | None = None
    predicted_utility: Any | None = None
    intent: AtuneEscalateIntent
    rollback_options: AtuneEscalateRollbackOptions | None = None
    episode_id: str | None = None


# ------------------------------------------------------------------------------

bridge = APIRouter()


@bridge.post("/escalate", name="atune_unity_bridge")
async def escalate(payload: AtuneEscalateRequest, request: Request) -> dict[str, Any]:
    """
    Atune-owned bridge to Unity. Translates its internal payload into a formal
    DeliberationSpec and transparently proxies the request and response,
    ensuring proper error handling and trace propagation.
    """
    # 1. Propagate critical tracing and budget headers.
    decision_id = request.headers.get("x-decision-id")
    budget_ms = request.headers.get("x-budget-ms", "8000")  # Increased default budget

    headers_to_forward = {"x-budget-ms": budget_ms}
    if decision_id:
        headers_to_forward["x-decision-id"] = decision_id

    # 2. Translate the incoming payload into the DeliberationSpec for Unity.
    try:
        reason_text = "N/A"
        raw_reason_json = None
        if payload.reason is None:
            reason_text = "N/A"
        elif isinstance(payload.reason, str):
            reason_text = payload.reason
        else:
            # dict or EscalationReason: serialize compactly; include kind up front if present
            try:
                if isinstance(payload.reason, EscalationReason):
                    raw = payload.reason.model_dump()
                else:
                    raw = payload.reason
                raw_reason_json = raw  # Keep the dict form for now
                kind = raw.get("kind")
                detail = raw.get("detail")
                head = f"{kind}: " if kind else ""
                reason_text = (
                    head
                    + json.dumps(
                        detail if detail is not None else raw,
                        ensure_ascii=False,
                    )[:800]
                )
            except Exception:
                reason_text = "structured reason (unserializable)"
        inputs = [
            InputRef(kind="text", value=f"Reason for escalation: {reason_text}"),
            InputRef(kind="doc", value=f"Predicted Utility: {payload.predicted_utility or 'N/A'}"),
            InputRef(
                kind="graph_ref",
                value=payload.intent.intent_id,
                meta={"label": "AxonIntent"},
            ),
        ]
        if raw_reason_json is not None:
            json_string_value = json.dumps(raw_reason_json, ensure_ascii=False)
            inputs.append(
                InputRef(kind="json", value=json_string_value, meta={"label": "EscalationReason"}),
            )
        constraints = payload.rollback_options.constraints if payload.rollback_options else []
        spec = DeliberationSpec(
            topic=f"Review of Escalated Intent: {payload.intent.intent_id}",
            goal="risk_review",
            inputs=inputs,
            constraints=constraints,
            episode_id=payload.episode_id,
            urgency="high",
        )
        deliberation_payload = spec.model_dump(mode="json")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to build DeliberationSpec: {e}")

    # 3. Call the downstream Unity service with robust error handling.
    try:
        # FIX: The `get_http_client` function is a coroutine and must be awaited.
        client = await get_http_client()
        response = await client.post(
            ENDPOINTS.UNITY_DELIBERATE,
            json=deliberation_payload,
            headers=headers_to_forward,
        )
        response.raise_for_status()
        # 4. Return Unity's response directly, fulfilling the bridge contract.
        return response.json()
    except httpx.HTTPStatusError as e:
        # The downstream service (Unity) returned a 4xx or 5xx error.
        # Propagate this as a 502 Bad Gateway.
        raise HTTPException(
            status_code=502,
            detail=f"Downstream error from Unity: {e.response.status_code} - {e.response.text}",
        )
    except httpx.RequestError as e:
        # A network error occurred (e.g., could not connect to Unity).
        # Propagate this as a 503 Service Unavailable.
        raise HTTPException(status_code=503, detail=f"Could not connect to Unity service: {e}")
