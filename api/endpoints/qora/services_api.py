# api/endpoints/qora/services_api.py
# MODIFIED FILE
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from systems.qora.core.services import constitution_service, deliberation_service, learning_service

# --- Constitution Router ---
constitution_router = APIRouter()
@constitution_router.get("/get")
async def get_constitution(agent: str = Query("Simula"), profile: str = Query("prod")):
    # ... (implementation from previous response)
    try:
        rules = await constitution_service.get_applicable_constitution(agent, profile)
        return {"ok": True, "rules": rules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get constitution: {e!r}")

# --- Deliberation Router ---
deliberation_router = APIRouter()
class CritiqueRequest(BaseModel):
    diff: str = Field(..., description="The unified diff to be reviewed.")
@deliberation_router.post("/critique")
async def request_critique(req: CritiqueRequest):
    # ... (implementation from previous response)
    try:
        result = await deliberation_service.request_critique(req.diff)
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Critique request failed: {e!r}")

# --- Learning Router (NEW) ---
learning_router = APIRouter()
class FindFailuresRequest(BaseModel):
    goal: str = Field(..., description="The current goal to find similar past failures for.")
    top_k: int = Field(3, ge=1, le=10)

@learning_router.post("/find_failures")
async def find_failures(req: FindFailuresRequest):
    """Endpoint for the agent to learn from past mistakes."""
    try:
        results = await learning_service.find_similar_failures(req.goal, req.top_k)
        return {"ok": True, "hits": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Finding similar failures failed: {e!r}")
