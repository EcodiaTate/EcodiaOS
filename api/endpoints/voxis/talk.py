# --- FINAL CORRECTED VERSION WITH STRONG LOGGING, SAFETY, AND HISTORY PAGINATION ---

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from core.utils.neo.cypher_query import cypher_query  # used by history endpoint
from systems.voxis.core.models import VoxisTalkRequest
from systems.voxis.core.pipeline import VoxisPipeline
from systems.voxis.core.result_store import AbstractResultStore, get_result_store

logger = logging.getLogger(__name__)
talk_router = APIRouter()


def _mint_decision_id() -> str:
    """Generates a unique, traceable ID for a single conversational turn."""
    return f"voxis-turn::{uuid4()}"


async def _run_pipeline_and_store(
    decision_id: str,
    req: VoxisTalkRequest,
    result_store: AbstractResultStore,
) -> None:
    """The core background task, designed for maximum resilience."""
    log_extra = {
        "decision_id": decision_id,
        "user_id": req.user_id,
        "session_id": req.session_id,
    }
    logger.info("[TalkBG] Start.", extra=log_extra)

    await result_store.update_field(decision_id, "status", "processing")

    try:
        pipeline = VoxisPipeline(req, result_store, decision_id)

        # Phase 1: Planning
        plan_and_context = await pipeline.run_planning_phase()
        if not plan_and_context or not plan_and_context[0]:
            raise RuntimeError("Planning phase failed to produce a plan.")

        # Small window so client can poll and get interim_thought
        await asyncio.sleep(0.1)

        # Phase 2: Execution and Synthesis
        data = await pipeline.run_execution_phase(plan_and_context)

        final_result = {
            "status": "succeeded",
            "decision_id": decision_id,
            "data": data,
        }
        await result_store.put(decision_id, final_result)
        logger.info("[TalkBG] Pipeline succeeded.", extra=log_extra)

    except Exception as e:
        logger.exception("[TalkBG] PIPELINE FAILED: %s", e, extra=log_extra)
        error_result = {
            "status": "failed",
            "decision_id": decision_id,
            "error": "An internal error occurred during processing. The event has been logged.",
        }
        await result_store.put(decision_id, error_result)


@talk_router.post("/talk", status_code=202)
async def voxis_talk_create(
    req: VoxisTalkRequest,
    request: Request,
    bg: BackgroundTasks,
    result_store: AbstractResultStore = Depends(get_result_store),
) -> dict[str, Any]:
    """
    Accepts a user interaction and initiates the cognitive cycle.
    The endpoint returns 202 + decision_id immediately, and the client polls /talk/result/{decision_id}.
    """
    client_ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "unknown")

    if not req.user_input or not req.user_input.strip():
        raise HTTPException(status_code=400, detail="User input cannot be empty.")

    # Strong log right at ingress
    logger.info(
        "[Talk] Ingress | ip=%s | ua=%s | user_id=%r | session_id=%r | input_len=%d | mode=%r",
        client_ip,
        ua,
        req.user_id,
        req.session_id,
        len(req.user_input or ""),
        req.output_mode,
    )

    decision_id = _mint_decision_id()
    log_extra = {"decision_id": decision_id, "user_id": req.user_id, "session_id": req.session_id}
    logger.info("[Talk] Accepted request.", extra=log_extra)

    initial_payload = {
        "status": "accepted",
        "decision_id": decision_id,
        "timestamp": time.time(),
    }
    await result_store.put(decision_id, initial_payload)

    # Kick off the background pipeline
    bg.add_task(_run_pipeline_and_store, decision_id, req, result_store)

    result_url = str(request.url_for("voxis_talk_get_result", result_id=decision_id))
    logger.info("[Talk] Handing 202 to client | poll=%s", result_url, extra=log_extra)

    return {"decision_id": decision_id, "result_url": result_url}


@talk_router.get("/talk/result/{result_id}", name="voxis_talk_get_result")
async def voxis_talk_get_result(
    result_id: str,
    result_store: AbstractResultStore = Depends(get_result_store),
):
    """
    Pollable endpoint for retrieving the result.
    - 202: Processing. May contain 'interim_thought'.
    - 200: Success with final payload.
    - 500: Pipeline failed.
    - 404: Unknown result_id.
    """
    result = await result_store.get(result_id)

    if not result:
        logger.warning("[TalkPoll] Unknown result_id: %s", result_id)
        raise HTTPException(status_code=404, detail=f"Unknown result_id: {result_id}")

    status = result.get("status", "unknown")

    if status in ("accepted", "processing"):
        # Return the whole object so clients can read interim_thought as soon as it appears
        return JSONResponse(
            status_code=202,
            content=result,
        )

    if status == "failed":
        logger.error("[TalkPoll] Returning failure for %s", result_id)
        return JSONResponse(
            status_code=500,
            content={
                "error": result.get("error", "Unknown pipeline error"),
                "decision_id": result_id,
            },
        )

    logger.info("[TalkPoll] Returning success for %s", result_id)
    return JSONResponse(status_code=200, content=result.get("data", {}))


# ---------------------------------------------------------------------------
# NEW: Paginated chat history endpoint to support rolling window + scroll-up
# ---------------------------------------------------------------------------
@talk_router.get("/talk/history")
async def voxis_talk_history(
    session_id: str = Query(..., description="Conversation session id"),
    before: str | None = Query(
        None,
        description="ISO timestamp cursor; return messages strictly earlier than this ts",
    ),
    limit: int = Query(20, ge=1, le=200, description="Page size (default 30)"),
):
    """
    Returns a page of messages for a given session, ordered NEWEST → OLDEST.
    - If `before` is provided (ISO datetime), returns messages with ts < before.
    - If omitted, returns the latest `limit` messages.
    - Client can infer `has_more` as (len(result) == limit).
    Output schema (per item):
      {
        "id": "<elementId>",
        "role": "user" | "assistant",
        "content": "<text>",
        "created_at": "<ISO timestamp>"
      }
    """
    # Build a single Cypher with optional before clause (ts < before)
    cypher = """
    MATCH (t)
    WHERE (t:SoulInput OR t:SoulResponse)
      AND coalesce(t.session_id, t.event_id) = $sid
    WITH t, coalesce(t.timestamp, datetime({epochMillis:0})) AS ts
    WHERE $before_is_null OR ts < datetime($before)
    RETURN
      elementId(t) AS id,
      CASE WHEN 'SoulInput' IN labels(t) THEN 'user' ELSE 'assistant' END AS role,
      t.text AS content,
      ts AS ts
    ORDER BY ts DESC
    LIMIT $lim
    """

    params: dict[str, Any] = {
        "sid": session_id,
        "before_is_null": before is None,
        "before": before or "",
        "lim": int(limit),
    }

    try:
        rows = await cypher_query(cypher, params) or []
        messages: list[dict[str, Any]] = []
        for r in rows:
            ts_val = r.get("ts")
            # Some drivers return temporal as native; ensure ISO str
            if hasattr(ts_val, "isoformat"):
                created_at = ts_val.isoformat()
            else:
                # fallback (could be string already)
                created_at = str(ts_val) if ts_val is not None else None

            messages.append(
                {
                    "id": r.get("id"),
                    "role": r.get("role"),
                    "content": r.get("content") or "",
                    "created_at": created_at,
                },
            )

        return JSONResponse(status_code=200, content=messages)
    except Exception as e:
        logger.exception("[TalkHistory] Query failed for session_id=%s: %s", session_id, e)
        raise HTTPException(status_code=500, detail="Failed to load history")
