from __future__ import annotations

from typing import Any

from systems.unity.core.policy import safety_policy


def safety_veto(*texts: str) -> tuple[bool, list[str]]:
    refs: list[str] = []
    for t in texts:
        v, rid, _ = safety_policy.check_prohibited(t or "")
        if v and rid:
            refs.append(rid)
    return (len(refs) > 0, list(sorted(set(refs))))


def constraint_check(constraints: list[Any] | None, draft: str) -> tuple[bool, list[str]]:
    """
    Returns (violates, reasons). Very simple policy:
    - If constraints include strings like 'must_not_approve' or 'require_mitigation', enforce them.
    Extend this to your Equor/constitution format as needed.
    """
    reasons: list[str] = []
    cs = constraints or []
    if isinstance(cs, dict):
        cs = [cs]
    flat = [str(c).lower() for c in cs]
    if any("must_not_approve" in c for c in flat):
        reasons.append("Constraint: must_not_approve")
    if any("require_mitigation" in c for c in flat) and "mitigation" not in draft.lower():
        reasons.append("Constraint: mitigation missing")
    return (len(reasons) > 0, reasons)
