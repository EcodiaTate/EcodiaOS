from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

hygiene_router = APIRouter()


# ---- Pydantic I/O Schemas (API-facing only) ---------------------------------


class HygieneRequest(BaseModel):
    diff: str = Field(..., description="Unified diff (for changed paths & -k expr)")
    auto_heal: bool = True
    timeout_sec: int = Field(900, ge=120, le=3600)


class RunStatus(BaseModel):
    status: str = Field(..., description="success | failure | error | skipped | unknown")
    summary: str | None = Field(default=None, description="Brief human summary")
    details: dict[str, Any] = Field(default_factory=dict, description="Raw tool payload")


class AutoHealLog(BaseModel):
    applied: bool = False
    status: dict[str, str] = Field(default_factory=dict)  # {"static": "...", "tests": "..."}
    diff_applied: str | None = None


class HygieneLogs(BaseModel):
    static: RunStatus
    tests: RunStatus
    auto_heal: AutoHealLog | None = None


class HygieneResponse(BaseModel):
    ok: bool
    static_status: str | None = None
    tests_status: str | None = None
    k_expr: str | None = None
    changed: list[str] = Field(default_factory=list)
    logs: HygieneLogs


# ---- Internal helpers (implementation details; NOT used in endpoint signature)


def _lazy_imports():
    """
    Import heavy/optional dependencies at call time so router import doesn't fail.
    Keeps endpoint signature clean (no callables or non-Pydantic params).
    """
    try:
        from systems.simula.code_sim.evaluators.impact import compute_impact  # type: ignore
    except Exception:
        compute_impact = None

    try:
        from systems.simula.nscs import agent_tools as _nscs  # type: ignore
    except Exception:
        _nscs = None

    return compute_impact, _nscs


def _as_run_status(payload: dict[str, Any] | None, fallback: str = "unknown") -> RunStatus:
    if not isinstance(payload, dict):
        return RunStatus(status=fallback, summary=None, details={"raw": payload})
    status = str(payload.get("status") or fallback)
    summary = payload.get("summary")
    return RunStatus(
        status=status, summary=summary if isinstance(summary, str) else None, details=payload
    )


# ---- Endpoint ----------------------------------------------------------------


@hygiene_router.post("/check", response_model=HygieneResponse)
async def hygiene_check(req: HygieneRequest) -> HygieneResponse:
    compute_impact, _nscs = _lazy_imports()
    if compute_impact is None or _nscs is None:
        # Keep explicit 501 to indicate feature unavailable in this deployment
        raise HTTPException(status_code=501, detail="impact or NSCS tools unavailable")

    # Impact analysis to find changed paths and a pytest -k expression
    imp = compute_impact(req.diff, workspace_root=".")
    changed: list[str] = list(imp.changed) if getattr(imp, "changed", None) else ["."]
    k_expr: str = getattr(imp, "k_expr", "") or ""

    # Static analysis
    static_res = await _nscs.static_check(paths=changed)
    static_status = str(static_res.get("status", "unknown"))

    # Tests: try targeted -k first (if available), else fall back to xdist
    tests_res = None
    if k_expr:
        tests_res = await _nscs.run_tests_k(
            paths=["tests"], k_expr=k_expr, timeout_sec=req.timeout_sec
        )
    if not tests_res or tests_res.get("status") != "success":
        tests_res = await _nscs.run_tests_xdist(paths=["tests"], timeout_sec=req.timeout_sec)
    tests_status = str(tests_res.get("status", "unknown"))

    # Optional auto-heal loop
    heal_log: AutoHealLog | None = None
    if req.auto_heal and (static_status != "success" or tests_status != "success"):
        apply_refactor_smart = getattr(_nscs, "apply_refactor_smart", None)
        diff_applied: str | None = None
        if callable(apply_refactor_smart):
            heal = await apply_refactor_smart(paths=changed)
            if isinstance(heal, dict) and heal.get("diff"):
                diff_applied = str(heal["diff"])
                # Apply and re-run checks
                _ = await _nscs.apply_refactor(diff=diff_applied, verify_paths=["tests"])
                static_res = await _nscs.static_check(paths=changed)
                tests_res = await _nscs.run_tests_xdist(
                    paths=["tests"], timeout_sec=req.timeout_sec
                )
                static_status = str(static_res.get("status", "unknown"))
                tests_status = str(tests_res.get("status", "unknown"))

        heal_log = AutoHealLog(
            applied=diff_applied is not None,
            diff_applied=diff_applied,
            status={"static": static_status, "tests": tests_status},
        )

    logs = HygieneLogs(
        static=_as_run_status(static_res),
        tests=_as_run_status(tests_res),
        auto_heal=heal_log,
    )

    ok = static_status == "success" and tests_status == "success"

    return HygieneResponse(
        ok=ok,
        static_status=static_status,
        tests_status=tests_status,
        k_expr=k_expr or None,
        changed=changed,
        logs=logs,
    )
