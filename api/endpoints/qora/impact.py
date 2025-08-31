from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from systems.simula.config import settings

# Reuse Simula impact/coverage logic
try:
    from systems.simula.code_sim.evaluators.impact import compute_impact
except Exception:  # pragma: no cover
    compute_impact = None
try:
    from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
except Exception:  # pragma: no cover
    compute_delta_coverage = None

impact_router = APIRouter(tags=["qora-impact"])


class ImpactPlanRequest(BaseModel):
    diff: str = Field(..., description="Unified diff text")
    include_coverage: bool = True


class ImpactPlanResponse(BaseModel):
    ok: bool
    plan: dict[str, Any] = Field(default_factory=dict)


def _risk_level(num_files: int, candidate_tests: int, delta_cov: float | None) -> str:
    risk = 0
    if num_files >= 10:
        risk += 2
    elif num_files >= 3:
        risk += 1
    if candidate_tests == 0:
        risk += 2
    if delta_cov is not None and delta_cov < 20.0:
        risk += 1
    return ["low", "medium", "high", "critical"][min(risk, 3)]


@impact_router.post("/plan", response_model=ImpactPlanResponse)
async def impact_plan(req: ImpactPlanRequest) -> ImpactPlanResponse:
    if compute_impact is None:
        raise HTTPException(status_code=501, detail="compute_impact unavailable in this build")
    try:
        imp = compute_impact(req.diff, workspace_root=str(settings.repo_root))
        changed = imp.changed or []
        k_expr = imp.k_expr or ""
        cand_tests = imp.candidate_tests or []
        suggestions: list[str] = []
        if k_expr:
            suggestions.append(f'pytest -k "{k_expr}" -q')
            if settings.use_xdist:
                suggestions.append(f'pytest -k "{k_expr}" -n auto -q')
        suggestions.append("pytest -q")
        if settings.use_xdist:
            suggestions.append("pytest -n auto -q")

        delta_cov_pct = None
        cov_summary = {}
        if req.include_coverage and compute_delta_coverage is not None:
            try:
                cov = compute_delta_coverage(req.diff)
                cov_summary = cov.summary()
                delta_cov_pct = float(cov_summary.get("pct_changed_covered", 0.0))
            except Exception:
                cov_summary = {}

        risk = _risk_level(len(changed), len(cand_tests), delta_cov_pct)
        plan = {
            "changed_paths": changed,
            "k_expr": k_expr,
            "candidate_tests": cand_tests,
            "suggested_commands": suggestions,
            "coverage_delta": cov_summary,
            "risk": risk,
        }
        return ImpactPlanResponse(ok=True, plan=plan)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"impact_plan failed: {e!r}")
