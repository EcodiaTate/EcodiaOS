# systems/simula/code_sim/evaluators/__init__.py
# --- PROJECT SENTINEL UPGRADE ---
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from . import contracts as _contracts
from . import perf as _perf
from . import runtime as _runtime
from . import static as _static
from . import tests as _tests


@dataclass
class EvalResult:
    """
    Canonical evaluator aggregate for the verification gauntlet.
    All scores are normalized to [0,1]. hard_gates_ok determines commit eligibility.
    """

    hard_gates_ok: bool
    raw: dict[str, Any]

    def as_dict(self) -> dict:
        """Returns the evaluation result as a dictionary."""
        return asdict(self)

    # --- Convenience properties for easy access to key metrics ---
    @property
    def unit_pass_ratio(self) -> float:
        return float(self.raw.get("tests", {}).get("unit", {}).get("ratio", 0.0))

    @property
    def static_score(self) -> float:
        s = self.raw.get("static", {})
        parts = [1.0 if s.get(k) else 0.0 for k in ["ruff_ok", "mypy_ok"]]
        return sum(parts) / len(parts) if parts else 0.0

    @property
    def security_score(self) -> float:
        return 1.0 if self.raw.get("static", {}).get("bandit_ok") else 0.0

    @property
    def contracts_score(self) -> float:
        c = self.raw.get("contracts", {})
        parts = [1.0 if c.get(k) else 0.0 for k in ["exports_ok", "registry_ok"]]
        return sum(parts) / len(parts) if parts else 0.0

    def summary(self) -> dict[str, Any]:
        """Provides a clean, flat summary of the evaluation for logging and observation."""
        return {
            "hard_gates_ok": self.hard_gates_ok,
            "unit_pass_ratio": self.unit_pass_ratio,
            "static_score": self.static_score,
            "security_score": self.security_score,
            "contracts_score": self.contracts_score,
            "raw_outputs": {
                "tests": self.raw.get("tests", {}).get("stdout", "N/A")[-1000:],
                "static": self.raw.get("static", {}).get("outputs", {}),
            },
        }


def run_evaluator_suite(objective: dict[str, Any], sandbox_session) -> EvalResult:
    """
    Executes the full evaluator ensemble inside the provided sandbox session.
    """
    tests = _tests.run(objective, sandbox_session)
    static = _static.run(objective, sandbox_session)
    contracts = _contracts.run(objective, sandbox_session)
    runtime = _runtime.run(objective, sandbox_session)
    perf = _perf.run(objective, sandbox_session)

    # Define the conditions for passing the hard gates
    unit_ok = bool(tests.get("ok"))
    contracts_ok = bool(contracts.get("exports_ok"))
    security_ok = bool(static.get("bandit_ok"))
    runtime_ok = bool(runtime.get("start_ok"))
    hard_ok = all([unit_ok, contracts_ok, security_ok, runtime_ok])

    raw = {
        "tests": tests,
        "static": static,
        "contracts": contracts,
        "runtime": runtime,
        "perf": perf,
    }
    return EvalResult(hard_gates_ok=hard_ok, raw=raw)
