# api/endpoints/qora/coverage_quick.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

coverage_quick_router = APIRouter(tags=["qora", "coverage"])

try:
    from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
except Exception:  # pragma: no cover
    compute_delta_coverage = None


class CovReq(BaseModel):
    diff: str = Field(..., description="Unified diff")


@coverage_quick_router.post("/delta", response_model=dict[str, Any])
async def delta(req: CovReq) -> dict[str, Any]:
    if compute_delta_coverage is None:
        raise HTTPException(status_code=501, detail="coverage_delta not available")
    cov = compute_delta_coverage(req.diff)
    summary: dict[str, Any]
    try:
        summary = cov.summary()
    except Exception:
        summary = {}
    return {"ok": True, "summary": summary}
