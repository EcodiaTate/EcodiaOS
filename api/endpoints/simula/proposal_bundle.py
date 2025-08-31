# api/endpoints/proposal_bundle.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from systems.simula.agent import qora_adapters as _qora

router = APIRouter(tags=["simula"])


class BundleReq(BaseModel):
    proposal: dict[str, Any] = Field(..., description="Proposal object from orchestrator")
    include_snapshot: bool = True
    min_delta_cov: float = 0.0
    add_safety_summary: bool = True


@router.post("/proposal/bundle")
async def proposal_bundle(req: BundleReq) -> dict[str, Any]:
    res = await _qora.qora_proposal_bundle(
        proposal=req.proposal,
        include_snapshot=req.include_snapshot,
        min_delta_cov=req.min_delta_cov,
        add_safety_summary=req.add_safety_summary,
    )
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("reason", "bundle failed"))
    return {"status": "success", "result": res.get("result")}
