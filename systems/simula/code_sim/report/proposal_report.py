# systems/simula/code_sim/report/proposal_report.py
from __future__ import annotations

from typing import Any


def _kv(d: dict[str, Any], keys: list[str]) -> str:
    parts = []
    for k in keys:
        v = d.get(k)
        if isinstance(v, float):
            parts.append(f"**{k}**: {v:.4f}")
        elif v is not None:
            parts.append(f"**{k}**: {v}")
    return " • ".join(parts)


def build_report_md(proposal: dict[str, Any]) -> str:
    ctx = proposal.get("context") or {}
    ev = proposal.get("evidence") or {}
    smt = ev.get("smt_verdict") or {}
    sim = ev.get("simulation") or {}
    hyg = ev.get("hygiene") or {}
    cov = ev.get("coverage_delta") or {}
    impact = ev.get("impact") or {}

    lines = []
    lines.append(f"# Proposal {proposal.get('proposal_id', '')}\n")
    lines.append("## Summary")
    lines.append(f"- Files changed: {len(impact.get('changed') or [])}")
    if impact.get("k_expr"):
        lines.append(f"- Focus tests (k): `{impact.get('k_expr')}`")
    lines.append("")
    lines.append("## SMT / Simulation")
    lines.append(f"- SMT: {_kv(smt, ['ok', 'reason'])}")
    lines.append(f"- Sim: {_kv(sim, ['p_success', 'p_safety_hit', 'reason'])}")
    lines.append("")
    lines.append("## Hygiene")
    lines.append(f"- Static: `{hyg.get('static')}`  •  Tests: `{hyg.get('tests')}`")
    if cov:
        pct = cov.get("pct_changed_covered", 0.0)
        lines.append(f"- ΔCoverage on changed lines: **{pct:.2f}%**")
    lines.append("")
    if ev.get("failing_tests"):
        lines.append("## Failing tests (parsed)")
        for ft in ev["failing_tests"]:
            name = ft.get("nodeid") or "unknown"
            msg = (ft.get("short") or "")[:240]
            lines.append(f"- `{name}` — {msg}")
        lines.append("")
    if ctx.get("diff"):
        lines.append("## Diff (excerpt)")
        diff_excerpt = "\n".join(ctx["diff"].splitlines()[:200])
        lines.append("```diff")
        lines.append(diff_excerpt)
        lines.append("```")
        lines.append("")
    return "\n".join(lines)
