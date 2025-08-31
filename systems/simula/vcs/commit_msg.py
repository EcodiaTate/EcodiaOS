# systems/simula/vcs/commit_msg.py
from __future__ import annotations


def render_conventional_commit(
    *,
    type_: str,
    scope: str | None,
    subject: str,
    body: str | None = None,
) -> str:
    head = f"{type_}{f'({scope})' if scope else ''}: {subject}".strip()
    if body:
        return head + "\n\n" + body.strip() + "\n"
    return head + "\n"


def title_from_evidence(evidence: dict[str, object]) -> str:
    hyg = (evidence or {}).get("hygiene") or {}
    tests = hyg.get("tests", "unknown")
    static = hyg.get("static", "unknown")
    cov = (evidence or {}).get("coverage_delta", {}).get("pct_changed_covered", 0)
    return f"simula: patch (tests={tests}, static={static}, Δcov={cov}%)"
