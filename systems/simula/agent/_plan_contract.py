# systems/simula/agent/_plan_contract.py  (new small module)

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, validator


# ----- schema for verification checks
class VerificationCheck(BaseModel):
    type: Literal["unit", "cli", "edge"]
    target: str | None = None  # e.g., "tests/unit/test_greeter.py::test_greet_basic"
    command: str | None = None
    expect_stdout: str | None = None
    expect_exit_code: int | None = 0

# ----- step schema (only allow safe actions; prefer patch over free write)
class PlanStep(BaseModel):
    action_type: Literal["read_file", "get_context_dossier", "apply_patch", "run_tests"]
    path: str | None = None
    target_fqname: str | None = None
    intent: str | None = None
    # unified diff patch (required if action_type == apply_patch)
    patch: str | None = None
    # run_tests convenience
    paths: str | None = None

    @validator("patch", always=True)
    def _patch_required_for_apply(cls, v, values):
        if values.get("action_type") == "apply_patch" and not (v and v.strip()):
            raise ValueError("apply_patch requires a unified diff in 'patch'.")
        return v

class PlanSpec(BaseModel):
    strategy_id: str = Field(..., min_length=3)
    strategy_rationale: str = Field(..., min_length=16)
    plan: list[PlanStep]
    verification_checks: list[VerificationCheck]
    rollback: dict = Field(default_factory=lambda: {"on_fail": "revert patch", "method": "git checkout -- tests/unit/test_greeter.py"})

    @validator("plan")
    def _no_freeform_write(cls, steps):
        for s in steps:
            if s.action_type == "apply_patch":
                # guard: patch must only touch tests/unit/test_greeter.py
                if "tests/unit/test_greeter.py" not in (s.patch or ""):
                    raise ValueError("patch must only affect tests/unit/test_greeter.py")
        return steps
