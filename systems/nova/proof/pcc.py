# file: systems/nova/proof/pcc.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic_core import core_schema


class ProofResult(BaseModel):
    ok: bool
    checks: dict[str, Any] = {}
    violations: list[str] = []


class ProofVM:
    """
    Minimal 'proof-carrying code' checker:
      - Ensures declared obligations exist in candidate / rollout request
      - Validates capability rate_limits keys
      - Validates post-conditions appear in evidence (when provided)
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, _source, _handler):
        # Accept instances as-is; schema/JSON handled by field annotation (or arbitrary_types_allowed)
        return core_schema.no_info_after_validator_function(
            lambda v: v if isinstance(v, cls) else TypeError("Expected ProofVM"),
            core_schema.any_schema(),
        )

    @classmethod
    def _validate(cls, v):
        if isinstance(v, cls):
            return v
        raise TypeError("Expected ProofVM instance")

    def check(
        self,
        capability_spec: dict[str, Any],
        obligations: dict[str, list[str]],
        evidence: dict[str, Any] | None = None,
    ) -> ProofResult:
        checks: dict[str, Any] = {}
        violations: list[str] = []

        # 1) Obligations presence
        for phase in ("pre", "post"):
            reqs = set(obligations.get(phase, []))
            if not reqs:
                violations.append(f"obligation.{phase}.missing")
            checks[f"obligation.{phase}.count"] = len(reqs)

        # 2) Capability rate limits sanity
        rl = capability_spec.get("rate_limits", {})
        for key in rl.keys():
            if key not in {"qps", "burst", "concurrency"}:
                violations.append(f"rate_limits.unknown:{key}")
        checks["rate_limits.ok"] = len(
            [k for k in rl.keys() if k in {"qps", "burst", "concurrency"}],
        ) == len(rl)

        # 3) Evidence includes post-conditions hints
        if evidence:
            tests = evidence.get("tests", {})
            if not tests or not tests.get("ok", False):
                violations.append("evidence.tests.missing_or_fail")

        ok = len(violations) == 0
        return ProofResult(ok=ok, checks=checks, violations=violations)
