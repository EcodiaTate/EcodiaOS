from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/qora/policy", tags=["qora-policy"])

try:
    from systems.simula.policy.eos_checker import check_diff_against_policies, load_policy_packs
except Exception:  # pragma: no cover
    load_policy_packs = None
    check_diff_against_policies = None


class DiffCheckRequest(BaseModel):
    diff: str = Field(..., description="unified diff text")
    policy_pack: str | None = Field(default=None, description="optional specific pack name")


class DiffCheckResponse(BaseModel):
    ok: bool
    summary: dict[str, Any]


@router.post("/check_diff", response_model=DiffCheckResponse)
async def check_diff(req: DiffCheckRequest) -> DiffCheckResponse:
    if not load_policy_packs or not check_diff_against_policies:
        raise HTTPException(status_code=501, detail="policy checker not wired in this build")
    try:
        packs = load_policy_packs(req.policy_pack)
        report = check_diff_against_policies(req.diff or "", packs)
        return DiffCheckResponse(ok=bool(getattr(report, "ok", False)), summary=report.summary())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"policy check failed: {e!r}")
