# ===== FILE: D:\EcodiaOS\api\endpoints\simula\risk.py =====
"""
REFACTORED:
- The `policy_ok` check no longer relies on `load_policy_packs` with
  hardcoded paths.
- It now uses the central `settings` object to determine where to find
  policy packs, ensuring consistent behavior.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# CORRECT: Import the settings object
from systems.simula.config import settings
from systems.simula.policy.packs import check_diff_against_policies, load_policy_packs
from systems.simula.risk.estimator import estimate_risk

router = APIRouter(tags=["simula"])


class RiskReq(BaseModel):
    diff: str = Field(..., description="Unified diff")
    static_ok: bool | None = None
    tests_ok: bool | None = None
    delta_cov_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    run_policy_check: bool = True
    simulate_p_success: float | None = Field(default=None, ge=0.0, le=1.0)


class RiskResp(BaseModel):
    risk: float
    grade: str
    features: dict[str, Any]
    files_sample: list[str]


@router.post("/risk/estimate", response_model=RiskResp)
async def risk_estimate(req: RiskReq):
    if not req.diff.strip():
        raise HTTPException(status_code=400, detail="diff must not be empty")

    policy_ok: bool | None = None
    if req.run_policy_check:
        try:
            # CORRECT: Load policies from paths defined in the central settings
            packs = load_policy_packs(settings.eos_policy_paths)
            rep = check_diff_against_policies(req.diff, packs)
            policy_ok = bool(getattr(rep, "ok", False))
        except Exception:
            policy_ok = None

    out = estimate_risk(
        diff_text=req.diff,
        policy_ok=policy_ok,
        static_ok=req.static_ok,
        tests_ok=req.tests_ok,
        delta_cov_pct=req.delta_cov_pct,
        simulate_p_success=req.simulate_p_success,
    )
    return RiskResp(**out)
