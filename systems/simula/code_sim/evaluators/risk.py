# systems/simula/code_sim/evaluators/risk.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HygieneStatus:
    static_ok: bool
    tests_ok: bool
    changed_count: int


def risk_score(hygiene: HygieneStatus, *, prior_bug_rate: float = 0.08) -> float:
    """
    Heuristic risk score in [0,1], higher means riskier.
    - penalize when static/tests fail
    - more changed files → higher risk
    - combine with prior bug rate
    """
    score = prior_bug_rate
    if not hygiene.static_ok:
        score += 0.3
    if not hygiene.tests_ok:
        score += 0.4
    score += min(0.3, hygiene.changed_count * 0.03)
    return max(0.0, min(1.0, score))


def summarize(hygiene_status: dict[str, object]) -> dict[str, object]:
    hs = HygieneStatus(
        static_ok=(hygiene_status.get("static") == "success"),
        tests_ok=(hygiene_status.get("tests") == "success"),
        changed_count=int(hygiene_status.get("changed_count") or 1),
    )
    return {"risk": risk_score(hs), "hygiene": hs.__dict__}
