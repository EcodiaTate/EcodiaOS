from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

plan_router = APIRouter()

# Optional deps from Simula/Qora; degrade gracefully.
try:
    from systems.simula.code_sim.evaluators.impact import compute_impact
except Exception:  # pragma: no cover
    compute_impact = None
try:
    from systems.qora.client import wm_search
except Exception:  # pragma: no cover
    wm_search = None


# ---------- models ----------
class DecomposeFromDiffRequest(BaseModel):
    diff: str = Field(..., description="Unified diff")
    include_search_hints: bool = True


class RoleStep(BaseModel):
    role: str
    summary: str
    args: dict[str, Any] = Field(default_factory=dict)


class DecomposeResponse(BaseModel):
    ok: bool
    plan: dict[str, Any] = Field(default_factory=dict)


class DecomposeFromGoalRequest(BaseModel):
    goal: str = Field(..., min_length=8)
    top_k: int = Field(15, ge=1, le=200)


# ---------- helpers ----------
def _mk_role_steps_from_impact(imp_obj) -> list[RoleStep]:
    changed = imp_obj.changed or []
    k_expr = imp_obj.k_expr or ""
    cand_tests = imp_obj.candidate_tests or []

    steps: list[RoleStep] = []

    steps.append(
        RoleStep(
            role="Architect",
            summary="Review changed paths and derive design invariants + risks.",
            args={"changed_paths": changed},
        ),
    )
    steps.append(
        RoleStep(
            role="Coder",
            summary="Implement changes behind feature flags where possible; ensure minimal blast radius.",
            args={"changed_paths": changed},
        ),
    )
    if k_expr:
        steps.append(
            RoleStep(
                role="QA",
                summary="Run focused tests and then full suite; triage failures.",
                args={"pytest_k": k_expr, "candidate_tests": cand_tests},
            ),
        )
    else:
        steps.append(
            RoleStep(
                role="QA",
                summary="Run full suite; derive a focused -k expression for the affected area.",
                args={"candidate_tests": cand_tests},
            ),
        )

    steps.append(
        RoleStep(
            role="Security",
            summary="Static scan of changed files for deserialization, subprocess, network, or path traversal risks.",
            args={"changed_paths": changed},
        ),
    )

    steps.append(
        RoleStep(
            role="Reviewer",
            summary="Policy check diff + produce PR-ready report.",
            args={"tools": ["qora_policy_check_diff", "qora_annotate_diff"]},
        ),
    )

    return steps


# ---------- endpoints ----------
@plan_router.post("/decompose_from_diff", response_model=DecomposeResponse)
async def decompose_from_diff(req: DecomposeFromDiffRequest) -> DecomposeResponse:
    if compute_impact is None:
        raise HTTPException(status_code=501, detail="compute_impact unavailable")
    try:
        imp = compute_impact(req.diff, workspace_root=".")
        steps = _mk_role_steps_from_impact(imp)

        hints: dict[str, Any] = {}
        if req.include_search_hints and callable(wm_search):
            hints = {}
            for p in imp.changed or []:
                stem = p.rsplit("/", 1)[-1].split(".")[0]
                try:
                    hits = await wm_search(q=stem, top_k=5)
                    hints[p] = hits.get("hits", [])
                except Exception:
                    hints[p] = []

        plan = {
            "changed_paths": imp.changed or [],
            "k_expr": imp.k_expr or "",
            "candidate_tests": imp.candidate_tests or [],
            "role_steps": [s.dict() for s in steps],
            "hints": hints,
        }
        return DecomposeResponse(ok=True, plan=plan)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"decompose_from_diff failed: {e!r}")


@plan_router.post("/decompose_from_goal", response_model=DecomposeResponse)
async def decompose_from_goal(req: DecomposeFromGoalRequest) -> DecomposeResponse:
    if not callable(wm_search):
        # Provide a minimal scaffold even without WM search.
        plan = {
            "changed_paths": [],
            "k_expr": "",
            "candidate_tests": [],
            "role_steps": [
                {
                    "role": "Architect",
                    "summary": "Clarify scope, constraints, and acceptance criteria.",
                    "args": {"goal": req.goal},
                },
                {
                    "role": "Coder",
                    "summary": "Create minimal PoC for core capability.",
                    "args": {"goal": req.goal},
                },
                {
                    "role": "QA",
                    "summary": "Draft scenario tests tied directly to acceptance.",
                    "args": {"goal": req.goal},
                },
            ],
            "hints": {},
        }
        return DecomposeResponse(ok=True, plan=plan)

    try:
        hits = await wm_search(q=req.goal, top_k=req.top_k)
        files = []
        for h in hits.get("hits", []):
            p = h.get("path")
            if p and p not in files:
                files.append(p)
            if len(files) >= 12:
                break

        plan = {
            "changed_paths": files,
            "k_expr": "",
            "candidate_tests": [],
            "role_steps": [
                {
                    "role": "Architect",
                    "summary": "Propose design with seam points and rollback plan.",
                    "args": {"seed_files": files},
                },
                {
                    "role": "Coder",
                    "summary": "Implement behind flags with unit tests per seam.",
                    "args": {"seed_files": files},
                },
                {
                    "role": "QA",
                    "summary": "Write focused tests for seeds + integration smoke.",
                    "args": {"seed_files": files},
                },
                {
                    "role": "Security",
                    "summary": "Threat-model new surfaces (inputs, network, subprocess).",
                    "args": {"seed_files": files},
                },
            ],
            "hints": {"search_hits": hits.get("hits", [])},
        }
        return DecomposeResponse(ok=True, plan=plan)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"decompose_from_goal failed: {e!r}")
