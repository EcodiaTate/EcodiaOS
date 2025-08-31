# api/endpoints/unity/deliberate.py
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from systems.unity.core.room.orchestrator import DeliberationManager
from systems.unity.schemas import DeliberationResponse, DeliberationSpec

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Singleton Dependency Injection ---
_manager_singleton: DeliberationManager | None = None

def get_deliberation_manager() -> DeliberationManager:
    """Provides the singleton DeliberationManager instance to the endpoint."""
    global _manager_singleton
    if _manager_singleton is None:
        _manager_singleton = DeliberationManager()
    return _manager_singleton

# --- Helper to read timeout from environment ---
def _env_timeout_seconds() -> float | None:
    """Safely reads and converts the timeout setting from environment variables."""
    raw = os.getenv("UNITY_DELIBERATION_TIMEOUT_MS")
    if not raw:
        return None
    try:
        return max(1.0, float(raw) / 1000.0)
    except (ValueError, TypeError):
        return None

# --- Main Endpoint ---
@router.post("/deliberate", response_model=DeliberationResponse)
async def start_deliberation(
    spec: DeliberationSpec,
    manager: DeliberationManager = Depends(get_deliberation_manager),
):
    """
    A thin, robust API wrapper that delegates the entire deliberation lifecycle
    to the canonical DeliberationManager.

    The manager is responsible for all business logic, including:
    - Safety checks
    - Protocol selection via Synapse
    - Protocol execution
    - Persistence of all artifacts and verdicts to Neo4j
    - Logging outcomes for learning
    """
    logger.info(
        "[Unity API] Request received for topic: '%s'",
        getattr(spec, "topic", "N/A"),
    )

    try:
        # The manager's run_session is the single source of truth for the entire process.
        timeout = _env_timeout_seconds()
        if timeout:
            result = await asyncio.wait_for(manager.run_session(spec), timeout=timeout)
        else:
            result = await manager.run_session(spec)

        # The manager's response is already in the correct shape.
        # Pydantic will validate it against the response_model.
        return result

    except asyncio.TimeoutError:
        err_msg = f"Deliberation timed out after {timeout} seconds."
        logger.error("[Unity API] %s (Topic: %s)", err_msg, spec.topic)
        raise HTTPException(status_code=504, detail=err_msg)
    
    except Exception as e:
        logger.exception("[Unity API] An unexpected error occurred during deliberation.")
        # This is a final safeguard. The manager has its own internal error handling,
        # but this catches any unhandled exceptions at the API boundary.
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred in the deliberation process: {e!r}",
        )