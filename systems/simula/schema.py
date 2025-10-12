# systems/simula/code_sim/specs/schema.py
# --- CONSOLIDATED AND UPGRADED TO PYDANTIC ---
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# =========================
# Leaf specs
# =========================


class Constraints(BaseModel):
    model_config = ConfigDict(extra="ignore")
    python: str = ">=3.10"
    allowed_new_packages: list[str] = Field(default_factory=list)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> Constraints:
        d = d or {}
        return Constraints(
            python=str(d.get("python", ">=3.10")),
            allowed_new_packages=list(d.get("allowed_new_packages") or []),
        )


class UnitTestsSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    paths: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> UnitTestsSpec:
        d = d or {}
        return UnitTestsSpec(
            paths=list(d.get("paths") or []),
            patterns=list(d.get("patterns") or []),
        )


class ContractsSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    must_export: list[str] = Field(default_factory=list)
    must_register: list[str] = Field(default_factory=list)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> ContractsSpec:
        d = d or {}
        return ContractsSpec(
            must_export=list(d.get("must_export") or []),
            must_register=list(d.get("must_register") or []),
        )


class DocsSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    files_must_change: list[str] = Field(default_factory=list)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> DocsSpec:
        d = d or {}
        return DocsSpec(files_must_change=list(d.get("files_must_change") or []))


class PerfSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pytest_duration_seconds: str | float = "<=30"

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> PerfSpec:
        d = d or {}
        return PerfSpec(pytest_duration_seconds=d.get("pytest_duration_seconds", "<=30"))


class AcceptanceSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    unit_tests: UnitTestsSpec = Field(default_factory=UnitTestsSpec)
    contracts: ContractsSpec = Field(default_factory=ContractsSpec)
    docs: DocsSpec = Field(default_factory=DocsSpec)
    perf: PerfSpec = Field(default_factory=PerfSpec)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> AcceptanceSpec:
        d = d or {}
        return AcceptanceSpec(
            unit_tests=UnitTestsSpec.from_dict(d.get("unit_tests")),
            contracts=ContractsSpec.from_dict(d.get("contracts")),
            docs=DocsSpec.from_dict(d.get("docs")),
            perf=PerfSpec.from_dict(d.get("perf")),
        )


class RuntimeSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    import_modules: list[str] = Field(default_factory=list)
    commands: list[list[str]] = Field(default_factory=list)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> RuntimeSpec:
        d = d or {}
        return RuntimeSpec(
            import_modules=list(d.get("import_modules") or []),
            commands=[list(x) for x in (d.get("commands") or [])],
        )


# =========================
# Objective / Step
# =========================
# NOTE: The definition for Objective/Step seems to be missing from the provided file.
# Assuming it exists or is not relevant to the current error.

# =========================
# Codegen API Schemas (Moved from api/endpoints/simula/jobs_codegen.py)
# =========================


class SimulaCodegenTarget(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str = Field(..., description="Repo-relative path")
    signature: str | None = Field(
        default=None, description="Optional symbol within the file (e.g., ClassName or func_name)"
    )


class SimulaCodegenIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    spec: str = Field(..., min_length=10)
    targets: list[SimulaCodegenTarget] = Field(default_factory=list)
    budget_ms: int | None = None
    # +++ FIX: Add the session_id to allow stateful, multi-turn interactions +++
    session_id: str | None = Field(
        default=None,
        description="An ID to track a multi-turn session. If not provided, a new one will be generated.",
    )


class SimulaCodegenOut(BaseModel):
    job_id: str
    status: str
    message: str | None = None


# Aliases for cross-system compatibility
CodegenRequest = SimulaCodegenIn
CodegenResponse = SimulaCodegenOut
