from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

shadow_run_router = APIRouter()

# Try Simula primitives (graceful fallback to subprocess)
try:
    from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
    from systems.simula.code_sim.evaluators.impact import compute_impact
    from systems.simula.nscs import agent_tools as _nscs  # static_check, run_tests_k/xdist
except Exception:  # pragma: no cover
    compute_impact = None
    compute_delta_coverage = None
    _nscs = None

try:
    from systems.simula.config import settings  # type: ignore

    REPO = Path(getattr(settings, "repo_root", ".")).resolve()
    ART = Path(getattr(settings, "artifacts_root", REPO / ".simula")).resolve()
except Exception:  # pragma: no cover
    REPO = Path(".").resolve()
    ART = (REPO / ".simula").resolve()


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 900) -> dict[str, Any]:
    cp = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {"rc": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}


@contextlib.contextmanager
def _worktree(head: str = "HEAD"):
    tmpdir = Path(tempfile.mkdtemp(prefix="simula-shadow-"))
    try:
        r = _run(["git", "worktree", "add", "--detach", str(tmpdir), head], cwd=REPO, timeout=120)
        if r["rc"] != 0:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise RuntimeError(r["stderr"] or r["stdout"])
        yield tmpdir
    finally:
        _run(["git", "worktree", "remove", "--force", str(tmpdir)], cwd=REPO, timeout=120)
        shutil.rmtree(tmpdir, ignore_errors=True)


class ShadowReq(BaseModel):
    diff: str = Field(..., description="Unified diff to evaluate")
    min_delta_cov: float = 0.0
    timeout_sec: int = Field(1200, ge=300, le=7200)
    run_safety: bool = True
    use_xdist: bool = True


class ShadowResp(BaseModel):
    ok: bool
    gates: dict[str, Any]
    logs: dict[str, Any]
    artifact_dir: str | None = None


def _static_fallback(cwd: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if shutil.which("ruff"):
        out["ruff"] = _run(["ruff", "check", "--quiet", "."], cwd=cwd, timeout=600)
    if shutil.which("mypy"):
        out["mypy"] = _run(
            ["mypy", "--hide-error-codes", "--no-color-output", "."],
            cwd=cwd,
            timeout=600,
        )
    status = "success" if all(v.get("rc", 1) == 0 for v in out.values()) else "fail"
    return {"status": status, **out}


def _tests_fallback(cwd: Path, k_expr: str, use_xdist: bool, timeout: int) -> dict[str, Any]:
    args = ["pytest", "-q"]
    if k_expr:
        args += ["-k", k_expr]
    if use_xdist and shutil.which("pytest"):
        # try xdist if available
        if shutil.which("pytest"):  # presence implies plugins may load; xdist optional
            args += ["-n", "auto", "--maxfail=1"]
    res = _run(args, cwd=cwd, timeout=timeout)
    return {
        "status": "success" if res["rc"] == 0 else "fail",
        "stdout": res["stdout"],
        "stderr": res["stderr"],
    }


@shadow_run_router.post("/run", response_model=ShadowResp)
async def shadow_run(req: ShadowReq) -> ShadowResp:
    if not (REPO / ".git").exists():
        raise HTTPException(status_code=400, detail=f"Not a git repo: {REPO}")

    out_dir = ART / "shadow_runs" / str(int(time.time()))
    out_dir.mkdir(parents=True, exist_ok=True)

    with _worktree("HEAD") as wt:
        # 1) apply diff
        ap = _run(["git", "apply", "--index", "--whitespace=fix", "-p0"], cwd=wt, timeout=120)
        if ap["rc"] != 0:
            ap2 = _run(["git", "apply", "--whitespace=fix", "-p0"], cwd=wt, timeout=120)
            if ap2["rc"] != 0:
                return ShadowResp(
                    ok=False,
                    gates={},
                    logs={"apply": ap2},
                    artifact_dir=str(out_dir),
                )

        # 2) impact (k-expr + changed)
        try:
            if compute_impact:
                imp = compute_impact(req.diff, workspace_root=str(wt))
                changed = imp.changed or ["."]
                k_expr = imp.k_expr or ""
            else:
                changed, k_expr = ["."], ""
        except Exception:
            changed, k_expr = ["."], ""

        # 3) static
        if _nscs:
            static_res = await _nscs.static_check(paths=changed)
        else:
            static_res = _static_fallback(wt)

        # 4) tests (k-focus then xdist fallback)
        if _nscs and k_expr:
            tests_res = await _nscs.run_tests_k(
                paths=["tests"],
                k_expr=k_expr,
                timeout_sec=req.timeout_sec,
            )
        else:
            tests_res = _tests_fallback(wt, k_expr, req.use_xdist, req.timeout_sec)
        if (not tests_res) or (tests_res.get("status") != "success"):
            if _nscs:
                tests_res = await _nscs.run_tests_xdist(
                    paths=["tests"],
                    timeout_sec=req.timeout_sec,
                )
            else:
                tests_res = _tests_fallback(wt, "", req.use_xdist, req.timeout_sec)

        # 5) coverage delta (diff-based, not cwd-dependent)
        try:
            cov = (
                compute_delta_coverage(req.diff).summary()
                if compute_delta_coverage
                else {"pct_changed_covered": 0.0}
            )
        except Exception:
            cov = {"pct_changed_covered": 0.0}

        # 6) safety (best-effort)
        safety = {}
        if req.run_safety:
            if shutil.which("bandit"):
                safety["bandit"] = _run(
                    ["bandit", "-q", "-f", "json", "-r", "."],
                    cwd=wt,
                    timeout=300,
                )
            if shutil.which("semgrep"):
                safety["semgrep"] = _run(
                    ["semgrep", "--error", "--json", "--quiet", "--config", "auto", "."],
                    cwd=wt,
                    timeout=300,
                )

    gates = {
        "static_ok": static_res.get("status") == "success",
        "tests_ok": tests_res.get("status") == "success",
        "delta_cov_pct": float(cov.get("pct_changed_covered", 0.0)),
        "delta_cov_ok": float(cov.get("pct_changed_covered", 0.0)) >= req.min_delta_cov,
    }
    ok = gates["static_ok"] and gates["tests_ok"] and gates["delta_cov_ok"]

    # persist logs
    (out_dir / "static.json").write_text(json.dumps(static_res, indent=2), encoding="utf-8")
    (out_dir / "tests.json").write_text(json.dumps(tests_res, indent=2), encoding="utf-8")
    (out_dir / "coverage.json").write_text(json.dumps(cov, indent=2), encoding="utf-8")
    (out_dir / "gates.json").write_text(json.dumps(gates, indent=2), encoding="utf-8")
    if safety:
        (out_dir / "safety.json").write_text(json.dumps(safety, indent=2), encoding="utf-8")

    return ShadowResp(
        ok=ok,
        gates=gates,
        logs={"static": static_res, "tests": tests_res, "coverage": cov, "safety": safety},
        artifact_dir=str(out_dir),
    )
