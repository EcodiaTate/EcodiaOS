from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

proposal_verify_router = APIRouter()

try:
    from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
    from systems.simula.code_sim.evaluators.impact import compute_impact  # k-expr, changed paths
    from systems.simula.nscs import agent_tools as _nscs  # static_check, run_tests_k/xdist
except Exception:  # pragma: no cover
    compute_impact = None
    compute_delta_coverage = None
    _nscs = None


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], timeout: int = 180) -> dict[str, Any]:
    try:
        cp = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)
        return {"rc": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "stdout": "", "stderr": "timeout"}


class VerifyReq(BaseModel):
    diff: str = Field(..., description="Unified diff for proposed change")
    min_delta_cov: float = Field(
        0.0,
        ge=0.0,
        le=100.0,
        description="Minimum % changed-lines coverage",
    )
    run_safety: bool = True
    semgrep_config: str = "auto"
    timeout_sec: int = Field(900, ge=120, le=3600)


class VerifyResp(BaseModel):
    ok: bool
    verdict: str
    reasons: list[str] = Field(default_factory=list)
    k_expr: str | None = None
    changed: list[str] = Field(default_factory=list)
    gates: dict[str, Any] = Field(default_factory=dict)
    logs: dict[str, Any] = Field(default_factory=dict)


@proposal_verify_router.post("/proposal/verify", response_model=VerifyResp)
async def proposal_verify(req: VerifyReq) -> VerifyResp:
    if any(v is None for v in (compute_impact, compute_delta_coverage, _nscs)):
        raise HTTPException(status_code=501, detail="impact/coverage/NSCS not available")

    reasons: list[str] = []
    gates: dict[str, Any] = {}

    # 1) Impact → changed paths + -k expression
    imp = compute_impact(req.diff, workspace_root=".")
    changed = imp.changed or ["."]
    k = imp.k_expr or ""

    # 2) Static + Tests (focused then xdist fallback)
    static_res = await _nscs.static_check(paths=changed)
    tests_res = (
        await _nscs.run_tests_k(paths=["tests"], k_expr=k, timeout_sec=req.timeout_sec)
        if k
        else None
    )
    if not tests_res or tests_res.get("status") != "success":
        tests_res = await _nscs.run_tests_xdist(paths=["tests"], timeout_sec=req.timeout_sec)

    gates["static_ok"] = static_res.get("status") == "success"
    gates["tests_ok"] = tests_res.get("status") == "success"
    if not gates["static_ok"]:
        reasons.append("static_check failed")
    if not gates["tests_ok"]:
        reasons.append("tests failed")

    # 3) Delta coverage
    cov = compute_delta_coverage(req.diff).summary()
    cov_pct = float(cov.get("pct_changed_covered", 0.0))
    gates["delta_cov_pct"] = cov_pct
    gates["delta_cov_ok"] = cov_pct >= req.min_delta_cov
    if not gates["delta_cov_ok"]:
        reasons.append(f"delta coverage {cov_pct:.2f}% < required {req.min_delta_cov:.2f}%")

    # 4) Safety (bandit/semgrep best-effort, no hard fail if tooling missing)
    safety: dict[str, Any] = {
        "bandit": {"available": _have("bandit")},
        "semgrep": {"available": _have("semgrep")},
    }
    if req.run_safety and safety["bandit"]["available"]:
        out = _run(
            ["bandit", "-q", "-f", "json", "-r", "."] + changed,
            timeout=min(240, req.timeout_sec),
        )
        try:
            payload = json.loads(out["stdout"] or "{}")
        except Exception:
            payload = {"raw": out}
        safety["bandit"]["report"] = payload
        safety["bandit"]["issues"] = (
            len(payload.get("results", [])) if isinstance(payload, dict) else None
        )
    if req.run_safety and safety["semgrep"]["available"]:
        out = _run(
            ["semgrep", "--error", "--json", "--quiet", "--config", req.semgrep_config, *changed],
            timeout=min(300, req.timeout_sec),
        )
        try:
            payload = json.loads(out["stdout"] or "{}")
        except Exception:
            payload = {"raw": out}
        safety["semgrep"]["report"] = payload
        safety["semgrep"]["issues"] = (
            len(payload.get("results") or []) if isinstance(payload, dict) else None
        )

    gates["safety"] = safety

    ok = gates["static_ok"] and gates["tests_ok"] and gates["delta_cov_ok"]
    verdict = "pass" if ok else "fail"
    return VerifyResp(
        ok=ok,
        verdict=verdict,
        reasons=reasons,
        k_expr=k or None,
        changed=changed,
        gates=gates,
        logs={"static": static_res, "tests": tests_res, "coverage": cov},
    )
