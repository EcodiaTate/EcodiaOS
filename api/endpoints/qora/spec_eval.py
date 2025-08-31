from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

spec_eval_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    ART = Path(getattr(settings, "artifacts_root", ".simula")).resolve()
except Exception:  # pragma: no cover
    ART = Path(".simula").resolve()

# Simula primitives (impact, hygiene)
try:
    from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
    from systems.simula.code_sim.evaluators.impact import compute_impact
    from systems.simula.nscs import agent_tools as _nscs
except Exception:  # pragma: no cover
    compute_impact = None
    compute_delta_coverage = None
    _nscs = None


class Candidate(BaseModel):
    id: str
    diff: str
    notes: str = ""


class SpecEvalReq(BaseModel):
    candidates: list[Candidate]
    min_delta_cov: float = Field(0.0, ge=0.0, le=100.0)
    timeout_sec: int = Field(900, ge=120, le=3600)
    max_parallel: int = Field(4, ge=1, le=32)
    score_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "tests_ok": 4.0,
            "static_ok": 2.0,
            "delta_cov_pct": 1.0,
            "footprint_inv": 0.5,  # smaller changed-set is slightly favored
        },
    )
    emit_markdown: bool = True


class CandidateResult(BaseModel):
    id: str
    ok: bool
    score: float
    changed: list[str] = Field(default_factory=list)
    k_expr: str | None = None
    static_ok: bool = False
    tests_ok: bool = False
    delta_cov_pct: float = 0.0
    notes: str = ""
    logs: dict[str, Any] = Field(default_factory=dict)


class SpecEvalResp(BaseModel):
    ok: bool
    champion_id: str | None
    scoreboard: list[CandidateResult]
    artifact_markdown: str | None = None


async def _eval_one(c: Candidate, req: SpecEvalReq) -> CandidateResult:
    # Impact
    imp = compute_impact(c.diff, workspace_root=".") if compute_impact else None
    changed = (imp.changed if imp else None) or ["."]
    k_expr = (imp.k_expr if imp else None) or None

    # Static
    static_res = await _nscs.static_check(paths=changed) if _nscs else {"status": "unknown"}
    static_ok = static_res.get("status") == "success"

    # Tests (k-focus then xdist)
    tests_res = None
    if _nscs and k_expr:
        tests_res = await _nscs.run_tests_k(
            paths=["tests"],
            k_expr=k_expr,
            timeout_sec=req.timeout_sec,
        )
    if not tests_res or tests_res.get("status") != "success":
        tests_res = (
            await _nscs.run_tests_xdist(paths=["tests"], timeout_sec=req.timeout_sec)
            if _nscs
            else {"status": "unknown"}
        )
    tests_ok = tests_res.get("status") == "success"

    # Coverage delta
    cov = (
        compute_delta_coverage(c.diff).summary()
        if compute_delta_coverage
        else {"pct_changed_covered": 0.0}
    )
    delta_cov_pct = float(cov.get("pct_changed_covered", 0.0))

    # Composite score
    w = req.score_weights
    footprint = max(len(changed), 1)
    score = (
        (w.get("tests_ok", 0) * (1.0 if tests_ok else 0.0))
        + (w.get("static_ok", 0) * (1.0 if static_ok else 0.0))
        + (w.get("delta_cov_pct", 0) * (delta_cov_pct / 100.0))
        + (w.get("footprint_inv", 0) * (1.0 / footprint))
    )

    # Minimum gates
    ok = tests_ok and static_ok and (delta_cov_pct >= req.min_delta_cov)

    return CandidateResult(
        id=c.id,
        ok=ok,
        score=score,
        changed=changed,
        k_expr=k_expr,
        static_ok=static_ok,
        tests_ok=tests_ok,
        delta_cov_pct=delta_cov_pct,
        notes=c.notes,
        logs={"static": static_res, "tests": tests_res, "coverage": cov},
    )


@spec_eval_router.post("/run", response_model=SpecEvalResp)
async def spec_eval_run(req: SpecEvalReq) -> SpecEvalResp:
    if any(v is None for v in (compute_impact, compute_delta_coverage, _nscs)):
        raise HTTPException(status_code=501, detail="impact/coverage/NSCS not available")
    if not req.candidates:
        raise HTTPException(status_code=400, detail="no candidates")

    sem = asyncio.Semaphore(req.max_parallel)

    async def _wrapped(cand: Candidate):
        async with sem:
            return await _eval_one(cand, req)

    results = await asyncio.gather(*[_wrapped(c) for c in req.candidates])
    results_sorted = sorted(results, key=lambda r: (r.ok, r.score), reverse=True)
    champ = results_sorted[0].id if results_sorted else None

    md_path = None
    if req.emit_markdown:
        ART.mkdir(parents=True, exist_ok=True)
        out = ART / "bundles" / f"spec-eval-{int(time.time())}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Speculative Evaluation Scoreboard\n\n"]
        lines.append("| id | ok | score | Δcov% | static | tests | changed |\n")
        lines.append("|---|---:|-----:|-----:|:-----:|:-----:|:--------|\n")
        for r in results_sorted:
            lines.append(
                f"| `{r.id}` | {('✅' if r.ok else '❌')} | {r.score:.3f} | {r.delta_cov_pct:.2f} | "
                f"{'✅' if r.static_ok else '❌'} | {'✅' if r.tests_ok else '❌'} | {len(r.changed)} |\n",
            )
        out.write_text("".join(lines), encoding="utf-8")
        md_path = str(out)

    return SpecEvalResp(
        ok=True,
        champion_id=champ,
        scoreboard=results_sorted,
        artifact_markdown=md_path,
    )
