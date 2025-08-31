from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Optional: pull candidate tests from Simula’s impact to enrich estimate
try:
    from systems.simula.code_sim.evaluators.impact import compute_impact
except Exception:  # pragma: no cover
    compute_impact = None

quality_router = APIRouter(tags=["qora-quality"])


class MutationEstimateRequest(BaseModel):
    diff: str = Field(..., description="Unified diff text")


class MutationEstimateResponse(BaseModel):
    ok: bool
    summary: dict[str, Any] = Field(default_factory=dict)


# very light operator sites detector on added lines
_OPS = [
    r"\b==\b",
    r"\b!=\b",
    r">=",
    r"<=",
    r">",
    r"<",
    r"\band\b",
    r"\bor\b",
    r"\b\+\b",
    r"\-\b",
    r"\*\b",
    r"\/\b",
]


@quality_router.post("/mutation_estimate", response_model=MutationEstimateResponse)
async def mutation_estimate(req: MutationEstimateRequest) -> MutationEstimateResponse:
    try:
        diff = req.diff or ""
        add_lines = [
            ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++ ")
        ]
        candidates = 0
        by_op: dict[str, int] = {}
        for ln in add_lines:
            for pat in _OPS:
                hits = len(re.findall(pat, ln))
                if hits:
                    candidates += hits
                    by_op[pat] = by_op.get(pat, 0) + hits

        cand_tests = 0
        k_expr = ""
        if compute_impact:
            try:
                imp = compute_impact(diff, workspace_root=".")
                cand_tests = len(imp.candidate_tests or [])
                k_expr = imp.k_expr or ""
            except Exception:
                pass

        # naive score: more candidate sites + more tests → better mutation score proxy
        # clamp 0..100
        score = min(100.0, max(5.0, (cand_tests * 7.0) + (max(0, 25 - candidates) * 2.0)))
        summary = {
            "estimated_mutation_score": round(score, 1),
            "mutant_sites": int(candidates),
            "by_operator": by_op,
            "candidate_tests": cand_tests,
            "k_expr": k_expr,
            "note": "Heuristic estimate; use Simula sandbox for true mutation runs.",
        }
        return MutationEstimateResponse(ok=True, summary=summary)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"mutation_estimate failed: {e!r}")
