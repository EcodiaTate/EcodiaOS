# systems/simula/review/pr_templates.py
from __future__ import annotations

import json
from typing import Any


def render_pr_body(*, title: str, evidence: dict[str, Any]) -> str:
    cov = evidence.get("coverage_delta") or {}
    hyg = evidence.get("hygiene") or {}
    policy = evidence.get("policy") or {}
    ddmin = evidence.get("ddmin") or {}
    auto = evidence.get("auto_repair") or {}
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "- Proposed by **Simula**.",
        "",
        "## Hygiene",
        f"- static: `{hyg.get('static')}`",
        f"- tests: `{hyg.get('tests')}`",
        "",
        "## Coverage (changed lines)",
        f"- {cov.get('pct_changed_covered', 0)}%",
        "",
    ]
    if policy:
        lines += ["## Policy", "```json", json.dumps(policy, indent=2), "```", ""]
    if ddmin:
        lines += ["## ddmin", "```json", json.dumps(ddmin, indent=2), "```", ""]
    if auto:
        lines += ["## auto_repair", "```json", json.dumps(auto, indent=2), "```", ""]
    return "\n".join(lines)
