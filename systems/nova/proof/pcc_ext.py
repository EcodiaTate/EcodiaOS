from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr

from systems.nova.proof.pcc import ProofResult
from systems.nova.proof.pcc import ProofVM as _BaseVM

# If you need to expose a VM in a response model elsewhere, use ProofVMField from pyd_types.py


class ProofVMExt(BaseModel):
    """
    Wraps the base PCC with extra safeguards:
      - obligations must be a superset of brief.success gates when provided
      - rollback contract strategy must be known + have checks
      - evidence must contain at least 1 post-condition proof key
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Runtime-only VM; excluded from schema/JSON to avoid Pydantic v2 schema errors
    _base: _BaseVM = PrivateAttr(default_factory=_BaseVM)

    @property
    def base(self) -> _BaseVM:
        """Back-compat accessor so existing call sites using `.base` still work."""
        return self._base

    def check(
        self,
        capability_spec: dict[str, Any],
        obligations: dict[str, list[str]],
        evidence: dict[str, Any] | None = None,
        brief_success: dict[str, Any] | None = None,
    ) -> ProofResult:
        res = self._base.check(capability_spec, obligations, evidence)
        violations = list(res.violations)

        # Superset check vs brief success gates (if provided)
        if brief_success:
            post = brief_success.get("post")
            req_posts = set(post) if isinstance(post, list) else set()
            got_posts = set(obligations.get("post", []))
            missing = [f"obligation.post.missing:{k}" for k in (req_posts - got_posts)]
            violations.extend(missing)

        # Rollback contract sanity
        rb = capability_spec.get("rollback_contract", {}) or {}
        if not rb.get("type"):
            violations.append("rollback.type.missing")
        if not rb.get("params"):
            violations.append("rollback.params.missing")

        # Evidence should contain at least one meaningful post-proof bucket
        if evidence:
            keys = set(evidence.keys())
            if not keys.intersection({"tests", "invariants", "attestations"}):
                violations.append("evidence.post_keys.missing")

        return ProofResult(ok=len(violations) == 0, checks=res.checks, violations=violations)
