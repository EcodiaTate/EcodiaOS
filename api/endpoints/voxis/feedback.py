# api/endpoints/voxis/feedback.py
# COMPLETE REPLACEMENT - WITH LOGGER IMPORT ADDED

from __future__ import annotations

import logging  # <-- IMPORT ADDED
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from core.services.synapse import synapse
from core.utils.neo.cypher_query import cypher_query

# Mount under /voxis so the final path is /voxis/feedback
feedback_router = APIRouter(tags=["voxis"])
logger = logging.getLogger(__name__)  # <-- LOGGER INITIALIZED

DEFAULT_TASK_KEY = "voxis_conversational_turn"


class FeedbackRequest(BaseModel):
    episode_id: str = Field(..., description="Episode id returned by planner/runner")
    utility: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="User feedback score: 1.0 for positive, 0.0 for negative.",
    )
    # Accept both; prefer arm_id if present
    arm_id: str | None = Field(None, description="The arm id used (dyn::<hash> or static)")
    chosen_arm_id: str | None = Field(None, description="Legacy: same as arm_id")
    # Optional passthrough for analytics/debug
    meta: dict[str, Any] | None = None


class FeedbackResponse(BaseModel):
    status: str = "ok"
    message: str = "Enriched feedback logged."
    routed: bool = True
    task_key: str | None = None


@feedback_router.post("/feedback", response_model=FeedbackResponse)
async def log_feedback(
    req: FeedbackRequest,
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        convert_underscores=False,
        alias="Idempotency-Key",
    ),
):
    """
    Receives explicit user feedback and enriches it with episode context, then logs a learning outcome to Synapse.
    """
    try:
        # --- 1) Normalize arm id from request ---
        arm_id = req.arm_id or req.chosen_arm_id

        # --- 2) Fetch episode details (task_key, chosen_arm_id) ---
        rows = await cypher_query(
            "MATCH (e:Episode {id: $episode_id}) RETURN e.task_key AS task_key, e.chosen_arm_id AS chosen_arm_id",
            {"episode_id": req.episode_id},
        )
        row = rows[0] if rows else {}
        if not row:
            logger.warning(
                f"[VOXIS FEEDBACK] Episode '{req.episode_id}' not found. Cannot log feedback."
            )
            # Return a different response for clarity if episode not found
            return FeedbackResponse(
                status="error", message="Episode ID not found.", routed=False, task_key=None
            )

        episode_task_key = row.get("task_key") or DEFAULT_TASK_KEY
        # Prefer explicit arm_id from request, then fall back to episode's recorded arm_id
        chosen_arm_id = arm_id or row.get("chosen_arm_id")

        if not chosen_arm_id:
            logger.warning(
                f"[VOXIS FEEDBACK] No arm_id could be resolved for episode '{req.episode_id}'; learning signal will be episode-only."
            )

        # --- 3) Build final metrics payload ---
        # The central RewardArbiter in Synapse will convert the 'utility' score into a [-1, 1] reward.
        final_metrics: dict[str, Any] = {
            "utility": req.utility,
            "success": req.utility,  # <--- key line
            "feedback_source": "user_explicit",
            "chosen_arm_id": chosen_arm_id,
        }

        if req.meta:
            final_metrics["meta"] = {
                **req.meta,
                "request_ip": getattr(request.client, "host", None),
                "user_agent": request.headers.get("user-agent"),
            }

        # --- 4) Log to Synapse ---
        routed = True
        try:
            await synapse.log_outcome(
                episode_id=req.episode_id,
                task_key=episode_task_key,
                metrics=final_metrics,
            )
        except Exception as e:
            logger.error(f"[VOXIS FEEDBACK] synapse.log_outcome failed: {e}")
            routed = False

        return FeedbackResponse(
            status="ok",
            message="Enriched feedback logged.",
            routed=routed,
            task_key=episode_task_key,
        )
    except Exception as e:
        logger.error(f"[Feedback Endpoint] Error logging outcome: {e}")
        return FeedbackResponse(
            status="error",
            message="Could not log feedback due to an internal server error.",
            routed=False,
            task_key=None,
        )
