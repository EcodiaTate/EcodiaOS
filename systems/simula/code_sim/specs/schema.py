# simula/code_sim/specs/schema.py
"""
Spec & Step Schema (stdlib only)

Goals
-----
- Provide strongly‑typed structures the whole code_sim stack can rely on.
- No third‑party deps (keep it pure dataclasses + validation helpers).
- Mirror fields already used by mutators/evaluators/orchestrator.

Key Types
---------
- Constraints
- UnitTestsSpec, ContractsSpec, DocsSpec, PerfSpec, AcceptanceSpec
- RuntimeSpec
- Objective
- StepTarget, Step

Conveniences
------------
- `Step.primary_target()` → (file_rel, export_name|None)
- `Objective.get(path, default)` → nested lookups
- `from_dict` constructors with defensive defaults
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =========================
# Leaf specs
# =========================


@dataclass
class Constraints:
    python: str = ">=3.10"
    allowed_new_packages: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> Constraints:
        d = d or {}
        return Constraints(
            python=str(d.get("python", ">=3.10")),
            allowed_new_packages=list(d.get("allowed_new_packages") or []),
        )


@dataclass
class UnitTestsSpec:
    paths: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> UnitTestsSpec:
        d = d or {}
        return UnitTestsSpec(
            paths=list(d.get("paths") or []),
            patterns=list(d.get("patterns") or []),
        )


@dataclass
class ContractsSpec:
    must_export: list[str] = field(default_factory=list)  # ["path.py::func(a:int)->R", ...]
    must_register: list[str] = field(
        default_factory=list,
    )  # ["registry: contains tool 'NAME'", ...]

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> ContractsSpec:
        d = d or {}
        return ContractsSpec(
            must_export=list(d.get("must_export") or []),
            must_register=list(d.get("must_register") or []),
        )


@dataclass
class DocsSpec:
    files_must_change: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> DocsSpec:
        d = d or {}
        return DocsSpec(
            files_must_change=list(d.get("files_must_change") or []),
        )


@dataclass
class PerfSpec:
    pytest_duration_seconds: str | float = "<=30"

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> PerfSpec:
        d = d or {}
        return PerfSpec(
            pytest_duration_seconds=d.get("pytest_duration_seconds", "<=30"),
        )


@dataclass
class AcceptanceSpec:
    unit_tests: UnitTestsSpec = field(default_factory=UnitTestsSpec)
    contracts: ContractsSpec = field(default_factory=ContractsSpec)
    docs: DocsSpec = field(default_factory=DocsSpec)
    perf: PerfSpec = field(default_factory=PerfSpec)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> AcceptanceSpec:
        d = d or {}
        return AcceptanceSpec(
            unit_tests=UnitTestsSpec.from_dict(d.get("unit_tests")),
            contracts=ContractsSpec.from_dict(d.get("contracts")),
            docs=DocsSpec.from_dict(d.get("docs")),
            perf=PerfSpec.from_dict(d.get("perf")),
        )


@dataclass
class RuntimeSpec:
    import_modules: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)

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


@dataclass
class Objective:
    title: str = ""
    description: str = ""
    acceptance: AcceptanceSpec = field(default_factory=AcceptanceSpec)
    runtime: RuntimeSpec = field(default_factory=RuntimeSpec)
    constraints: Constraints = field(default_factory=Constraints)
    extras: dict[str, Any] = field(default_factory=dict)  # for anything custom

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> Objective:
        d = d or {}
        # Pull nested known keys; the rest go into extras for mutators to use
        known = {"title", "description", "acceptance", "runtime", "constraints"}
        extras = {k: v for k, v in d.items() if k not in known}
        return Objective(
            title=str(d.get("title", "")),
            description=str(d.get("description", "")),
            acceptance=AcceptanceSpec.from_dict(d.get("acceptance")),
            runtime=RuntimeSpec.from_dict(d.get("runtime")),
            constraints=Constraints.from_dict(d.get("constraints")),
            extras=extras,
        )

    def get(self, *path: str, default: Any = None) -> Any:
        """
        Safe nested lookup: obj.get('acceptance','contracts','must_export', default=[]).
        """
        cur: Any = {
            "acceptance": self.acceptance,
            "runtime": self.runtime,
            "constraints": self.constraints,
            **self.extras,
        }
        for p in path:
            if cur is None:
                return default
            if hasattr(cur, p):
                cur = getattr(cur, p)
            elif isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return default
        return cur if cur is not None else default


@dataclass
class StepTarget:
    file: str
    export: str | None = None

    @staticmethod
    def from_dict(d: dict[str, Any]) -> StepTarget:
        return StepTarget(file=str(d.get("file", "")), export=d.get("export"))


@dataclass
class Step:
    name: str
    iterations: int = 1
    targets: list[StepTarget] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)  # optional override for which tests to run
    objective: dict[str, Any] = field(
        default_factory=dict,
    )  # raw dict view for mutators expecting dict
    constraints: Constraints = field(default_factory=Constraints)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Step:
        # Accept either full Objective dataclass or plain dict
        obj_dict = d.get("objective") or {}
        obj = Objective.from_dict(obj_dict)

        return Step(
            name=str(d.get("name", "step")),
            iterations=int(d.get("iterations", 1)),
            targets=[StepTarget.from_dict(t) for t in (d.get("targets") or [])],
            tests=list(
                d.get("tests")
                or obj.acceptance.unit_tests.paths
                or obj.acceptance.unit_tests.patterns
                or [],
            ),
            objective=obj_dict,  # keep raw dict for modules that expect a mapping
            constraints=obj.constraints,
        )

    # ---- Convenience API consumed by mutators/evaluators ----
    def primary_target(self) -> tuple[str | None, str | None]:
        if not self.targets:
            return None, None
        t = self.targets[0]
        return t.file, t.export

    @property
    def acceptance(self) -> AcceptanceSpec:
        return Objective.from_dict(self.objective).acceptance

    @property
    def runtime(self) -> RuntimeSpec:
        return Objective.from_dict(self.objective).runtime


@dataclass
class Plan:
    """
    Represents the final, validated, and executable plan.
    This is the top-level object returned by the planner, containing an
    ordered list of steps for the engine to execute.
    """

    steps: list[Step] = field(default_factory=list)
