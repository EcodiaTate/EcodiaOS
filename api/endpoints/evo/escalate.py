# api/endpoints/evo/escalate.py
# DESCRIPTION: Hardened version with detailed comments explaining the critical
# resiliency patterns like spam guarding and circular dependency checks.

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Header, HTTPException, Response

from systems.evo.runtime import get_engine
from systems.evo.schemas import ConflictNode, EscalationRequest, EscalationResult
from systems.qora.core.immune.auto_instrument import immune_section  # Critical for recursion safety

escalate_router = APIRouter(tags=["evo-escalate"])
_engine = get_engine()

# A simple in-memory cache to dampen duplicate requests from the same source.
# This prevents alert storms from a single, persistent issue.
_LAST_SEEN: dict[str, float] = {}
_SPAM_COOLDOWN_SEC = 30.0


def _spam_key(body: dict[str, Any]) -> str:
    """Creates a stable hash of the core request payload to detect duplicates."""
    blob = json.dumps(
        {
            "ids": sorted(body.get("conflict_ids") or []),
            "brief": body.get("brief_overrides", {}),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _seen_recently(key: str) -> bool:
    """Checks if a key has been seen within the cooldown window."""
    now = time.monotonic()
    if (now - _LAST_SEEN.get(key, 0.0)) < _SPAM_COOLDOWN_SEC:
        return True
    _LAST_SEEN[key] = now
    return False


@escalate_router.post("/escalate", name="escalate", response_model=EscalationResult)
async def escalate(
    payload: dict[str, Any] = Body(...),
    response: Response = ...,
    x_budget_ms: int | None = Header(None),
    x_decision_id: str | None = Header(None),
) -> Any:
    """
    The primary ingress for escalating conflicts to the Evo engine.
    This endpoint is heavily fortified with guards against recursion, spam, and bad data.
    """
    t0 = time.perf_counter()
    decision_id = x_decision_id or f"evo-dec-{uuid4().hex[:12]}"
    response.headers["X-Decision-Id"] = decision_id

    # GUARD 1: SPAM/DUPLICATE REQUESTS
    # If this exact request was seen recently, ignore it to prevent alert storms.
    # Return 202 Accepted to signal to the caller that the request was acknowledged
    # but not processed, which is not an error state.
    if _seen_recently(_spam_key(payload)):
        raise HTTPException(
            status_code=202,
            detail={"ignored": "duplicate_request", "decision_id": decision_id},
        )

    # Data Hydration & Validation
    conflict_ids = payload.get("conflict_ids", [])
    if not conflict_ids:
        raise HTTPException(status_code=422, detail="Request must include 'conflict_ids'.")

    # Run the core, potentially fallible, logic within an immune_section.
    # This prevents any exceptions from within the Evo engine's escalation
    # process from being re-reported as new conflicts, which would cause an
    # infinite loop. This is the most critical resiliency pattern.
    async with immune_section():
        try:
            budget = x_budget_ms if x_budget_ms is not None else payload.get("budget_ms")

            # The engine's run_cycle is the authoritative entry point.
            result_dict = await _engine.run_cycle(conflict_ids, budget_ms=budget)

            # Ensure the result conforms to the EscalationResult schema before returning.
            if result_dict.get("status") == "escalated_to_nova":
                result = EscalationResult.model_validate(result_dict["result"])
            else:
                # If it was a local repair or other status, return the dictionary.
                return result_dict

        except Exception as e:
            # Degrade gracefully. Never return a 500 error, which could cause
            # upstream systems to retry and amplify the problem. 202 Accepted is
            # a safe, non-error response.
            raise HTTPException(
                status_code=202,
                detail={
                    "degraded": "internal_engine_exception",
                    "message": str(e),
                    "decision_id": decision_id,
                },
            )

    response.headers["X-Cost-MS"] = str(int((time.perf_counter() - t0) * 1000))
    return result
