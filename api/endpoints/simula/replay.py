# api/endpoints/simula/replay.py
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
from systems.simula.code_sim.evaluators.impact import compute_impact

# Simula sandbox + utilities
from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config

replay_router = APIRouter()


# --------- Schemas ---------
class ReplayReq(BaseModel):
    # Git ref/sha/tag to replay against (optional). If not provided, uses the sandbox seed default (usually HEAD).
    base_ref: str | None = Field(default=None)
    # Unified diff to apply and test.
    diff: str = Field(..., description="Unified diff to apply before running tests.")
    # Optional pytest -k expression to focus tests
    k_expr: str | None = None
    # Gate: require at least this % of changed lines covered (0..100)
    min_delta_cov: float = 0.0
    # Timeout for test runs (seconds)
    timeout_sec: int = Field(1200, ge=300, le=7200)
    # Whether to collect coverage and compute delta coverage
    collect_coverage: bool = True


class ReplayResp(BaseModel):
    ok: bool
    gates: dict[str, Any] = Field(default_factory=dict)
    logs: dict[str, Any] = Field(default_factory=dict)
    artifact_dir: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# --------- Endpoint ---------
@replay_router.post("/historical-replay", response_model=ReplayResp)
async def historical_replay(req: ReplayReq) -> ReplayResp:
    """
    Apply a unified diff on top of an optional base git ref and execute tests *inside* DockerSandbox.
    Produces optional delta coverage metrics (changed lines covered).
    """
    # Prepare sandbox configuration (optionally pin a git ref if your seed supports it)
    try:
        cfg = seed_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"seed_config failed: {e!r}")

    t0 = time.time()
    async with DockerSandbox(cfg).session() as sess:
        # 1) (Optional) Checkout historical base
        if req.base_ref:
            # Best-effort: support multiple sandbox APIs for git checkout
            checked_out = False
            for method_name, args in [
                ("git_checkout", (req.base_ref,)),
                ("checkout_git_ref", (req.base_ref,)),
                ("checkout", ("git", req.base_ref)),
            ]:
                try:
                    m = getattr(sess, method_name)  # type: ignore[attr-defined]
                    r = await m(*args)  # type: ignore[misc]
                    # Some APIs return bool, some dict — be liberal:
                    if r is None or r is True or (isinstance(r, dict) and r.get("ok", True)):
                        checked_out = True
                        break
                except AttributeError:
                    continue
                except Exception:
                    continue
            if not checked_out:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to checkout base_ref={req.base_ref}",
                )

        # 2) Apply diff
        applied = await sess.apply_unified_diff(req.diff)
        if not applied:
            raise HTTPException(status_code=400, detail="Failed to apply diff in sandbox")

        # 3) Test execution (k-focused first, fallback to full/xdist)
        tests_res: dict[str, Any] = {}
        # Try to derive a focused -k expression from impact if caller didn't provide one
        k_expr = req.k_expr
        if not k_expr:
            try:
                imp = compute_impact(req.diff, workspace_root=".")
                k_expr = imp.k_expr or None
            except Exception:
                k_expr = None

        # prefer focused run if available
        try:
            if k_expr and hasattr(sess, "run_pytest_select"):
                tests_res = await sess.run_pytest_select(
                    ["tests"],
                    k_expr=k_expr,
                    timeout=req.timeout_sec,
                )  # type: ignore[attr-defined]
        except Exception:
            tests_res = {}

        # fallback to xdist or plain pytest in sandbox
        if not tests_res or tests_res.get("status") != "success":
            try:
                if hasattr(sess, "run_pytest_xdist"):
                    tests_res = await sess.run_pytest_xdist(["tests"], timeout=req.timeout_sec)  # type: ignore[attr-defined]
                else:
                    tests_res = await sess.run_pytest(["tests"], timeout=req.timeout_sec)  # type: ignore[attr-defined]
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"pytest failed in sandbox: {e!r}")

        # 4) Coverage (optional) + delta coverage against diff
        cov_summary: dict[str, Any] = {}
        if req.collect_coverage:
            try:
                if hasattr(sess, "run_pytest_coverage"):
                    # If your sandbox supports include patterns, you can pass impact.changed here
                    await sess.run_pytest_coverage(
                        ["tests"],
                        include=None,
                        timeout=min(900, req.timeout_sec),
                    )  # type: ignore[attr-defined]
                cov_summary = compute_delta_coverage(req.diff).summary()
            except Exception:
                cov_summary = {"pct_changed_covered": 0.0}

    # 5) Gates
    tests_ok = tests_res.get("status") == "success"
    delta_cov_pct = float(cov_summary.get("pct_changed_covered", 0.0))
    cov_ok = (delta_cov_pct >= float(req.min_delta_cov)) if req.collect_coverage else True

    gates = {
        "tests_ok": tests_ok,
        "delta_cov_pct": delta_cov_pct,
        "delta_cov_ok": cov_ok,
        "min_delta_cov": req.min_delta_cov,
    }
    ok = tests_ok and cov_ok

    meta = {"elapsed_sec": round(time.time() - t0, 3), "base_ref": req.base_ref}
    return ReplayResp(
        ok=ok,
        gates=gates,
        logs={"tests": tests_res, "coverage": cov_summary},
        artifact_dir=None,
        meta=meta,
    )
