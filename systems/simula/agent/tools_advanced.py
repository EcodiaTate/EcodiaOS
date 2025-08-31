# systems/simula/agent/tools_advanced.py
from __future__ import annotations

from typing import Any

from systems.simula.build.run import run_build_and_tests
from systems.simula.format.autoformat import autoformat_changed
from systems.simula.git.rebase import rebase_diff_onto_branch
from systems.simula.recipes.generator import append_recipe
from systems.simula.search.portfolio_runner import rank_portfolio


async def format_patch(params: dict[str, Any]) -> dict[str, Any]:
    paths = params.get("paths") or []
    return await autoformat_changed(paths)


async def rebase_patch(params: dict[str, Any]) -> dict[str, Any]:
    diff = params.get("diff") or ""
    base = params.get("base") or "origin/main"
    return await rebase_diff_onto_branch(diff, base=base)


async def local_select_patch(params: dict[str, Any]) -> dict[str, Any]:
    cands = params.get("candidates") or []
    topk = int(params.get("top_k") or 3)
    ranked = await rank_portfolio(cands, top_k=topk)
    return {"status": "success", "top": ranked}


async def record_recipe(params: dict[str, Any]) -> dict[str, Any]:
    r = append_recipe(
        goal=params.get("goal", ""),
        context_fqname=params.get("context_fqname", ""),
        steps=params.get("steps") or [],
        success=bool(params.get("success", True)),
        impact_hint=params.get("impact_hint", ""),
    )
    return {"status": "success", "recipe": r.__dict__}


async def run_ci_locally(params: dict[str, Any]) -> dict[str, Any]:
    return await run_build_and_tests(
        paths=params.get("paths") or None,
        timeout_sec=int(params.get("timeout_sec") or 2400),
    )
