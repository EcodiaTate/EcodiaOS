# systems/simula/code_sim/portfolio/__init__.py  (include structural strategies)
from __future__ import annotations

from typing import Any, Dict, List

from .strategies import generate_candidates as _gen_basic
from .strategies_structural import generate_structural_candidates as _gen_struct


async def generate_candidate_portfolio(
    *,
    job_meta: dict[str, Any],
    step: Any,
) -> list[dict[str, Any]]:
    desc = getattr(step, "name", None) or getattr(step, "desc", None) or str(step)
    target_file = "unknown.py"
    fn_name = None
    intent = "edit"
    if "::" in desc:
        parts = [p for p in desc.split("::") if p]
        intent = parts[0] if parts else "edit"
        target_file = parts[1] if len(parts) >= 2 else target_file
        fn_name = parts[2] if len(parts) >= 3 else None

    c_basic = _gen_basic(target_file, fn_name, intent=intent)
    c_struct = _gen_struct(target_file, fn_name)
    portfolio = []
    i = 0
    for c in (c_basic + c_struct)[:10]:
        portfolio.append(
            {
                "id": f"cand_{i}",
                "title": f"{c.risk.upper()}:{c.uid}",
                "diff": c.diff,
                "rationale": c.rationale,
                "risk": c.risk,
                "meta": {"generator": "simula.portfolio", **(c.meta or {})},
            },
        )
        i += 1
    return portfolio
