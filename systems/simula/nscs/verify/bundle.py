from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ProofBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    contracts_ok: bool = True
    types_ok: bool = True
    lint_ok: bool = True
    property_ok: bool = True
    smt_ok: bool = True
    perf_ok: bool = True
    coverage: float = 0.0
    artifacts: dict[str, Any] = {}


def summarize(bundle: ProofBundle) -> dict[str, Any]:
    ok = all(
        [
            bundle.contracts_ok,
            bundle.types_ok,
            bundle.lint_ok,
            bundle.property_ok,
            bundle.smt_ok,
            bundle.perf_ok,
        ],
    )
    return {"ok": ok, "coverage": bundle.coverage, "artifacts": bundle.artifacts}
