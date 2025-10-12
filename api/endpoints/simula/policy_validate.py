# api/endpoints/simula/policy_validate.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from systems.simula.config import settings
from systems.simula.policy.packs import check_diff_against_policies, load_policy_packs

router = APIRouter(tags=["simula"])


class PolicyValidateReq(BaseModel):
    # tolerate extra keys from callers/forwarders
    model_config = ConfigDict(extra="ignore")
    diff: str = Field(..., description="Unified diff text")


class PolicyValidateResp(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: bool
    findings: dict[str, Any]


@router.post("/validate", response_model=PolicyValidateResp)
async def policy_validate(req: PolicyValidateReq) -> PolicyValidateResp:
    if not req.diff.strip():
        raise HTTPException(status_code=400, detail="diff must not be empty")

    packs = load_policy_packs(settings.eos_policy_paths)
    report = check_diff_against_policies(req.diff, packs)

    return PolicyValidateResp(
        ok=bool(getattr(report, "ok", False)),
        findings=report.summary() if hasattr(report, "summary") else {},
    )
