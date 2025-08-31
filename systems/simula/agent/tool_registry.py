# ===== FILE: systems/simula/agent/tool_registry.py =====
"""
Unified Tool Registry & Adapter Resolver

- Prefer functions in `agent/tools.py` (_core) when they exist.
- Fall back to `nscs/agent_tools.py` (_nscs) or `agent/qora_adapters.py` (_qora).
- Handles aliases like ("write_code" -> "write_file") and
  ("run_fuzz_smoke" -> "run_hypothesis_smoke").
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from systems.simula.agent import tools as _core
from systems.simula.nscs import agent_tools as _nscs
from systems.simula.agent import qora_adapters as _qora


def _wrap(func: Callable[..., Any]) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Normalize call style to: await wrapped({'k': v}) for both kwargs-style and params-dict-style tools."""
    sig = inspect.signature(func)
    is_async = inspect.iscoroutinefunction(func)
    params = list(sig.parameters.values())
    call_as_params_dict = len(params) == 1 and params[0].name in {"params", "payload"}

    async def runner(payload: dict[str, Any]) -> dict[str, Any]:
        payload = payload or {}
        call = func(payload) if call_as_params_dict else func(**payload)
        return await call if is_async else call  # type: ignore[return-value]

    return runner


def _resolve(*names: str) -> Callable[..., Any]:
    """
    Return the first callable found by name across core → nscs → qora.
    You may pass multiple names to support aliases (first match wins).
    """
    modules = (_core, _nscs, _qora)
    for name in names:
        for mod in modules:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn
    mods = ", ".join(m.__name__ for m in modules)
    al = " | ".join(names)
    raise ImportError(f"Tool '{al}' not found in any module: {mods}")


TOOLS: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    # ---------------- Core / NSCS (auto-resolved) ----------------
    "get_context_dossier": _wrap(_resolve("get_context_dossier")),
    "memory_write": _wrap(_resolve("memory_write")),
    "memory_read": _wrap(_resolve("memory_read")),

    "generate_tests": _wrap(_resolve("generate_tests")),
    "static_check": _wrap(_resolve("static_check")),
    "run_tests": _wrap(_resolve("run_tests")),
    "run_tests_k": _wrap(_resolve("run_tests_k")),
    "run_tests_xdist": _wrap(_resolve("run_tests_xdist")),

    # Canonical write op; prefer explicit 'write_code', fallback to legacy 'write_file'
    "write_code": _wrap(_resolve("write_code", "write_file")),
    "open_pr": _wrap(_resolve("open_pr")),
    "package_artifacts": _wrap(_resolve("package_artifacts")),
    "policy_gate": _wrap(_resolve("policy_gate")),
    "impact_and_cov": _wrap(_resolve("impact_and_cov")),
    "render_ci_yaml": _wrap(_resolve("render_ci_yaml")),
    "conventional_commit_title": _wrap(_resolve("conventional_commit_title")),
    "conventional_commit_message": _wrap(_resolve("conventional_commit_message")),
    "format_patch": _wrap(_resolve("format_patch")),
    "rebase_patch": _wrap(_resolve("rebase_patch")),
    "local_select_patch": _wrap(_resolve("local_select_patch")),
    "record_recipe": _wrap(_resolve("record_recipe")),
    "run_ci_locally": _wrap(_resolve("run_ci_locally")),

    # Prefer the local sandbox-aware apply_refactor; fall back to NSCS if absent
    "apply_refactor_smart": _wrap(_resolve("apply_refactor_smart")),
    "apply_refactor": _wrap(_resolve("apply_refactor")),

    # Repair/fuzz helpers (support legacy hypo name)
    "run_repair_engine": _wrap(_resolve("run_repair_engine")),
    "run_fuzz_smoke": _wrap(_resolve("run_fuzz_smoke", "run_hypothesis_smoke")),

    # ---------------- Qora HTTP wrappers (in agent/tools.py) ----------------
    "execute_system_tool": _wrap(_resolve("execute_system_tool")),
    "execute_system_tool_strict": _wrap(_resolve("execute_system_tool_strict")),
    "continue_hierarchical_skill": _wrap(_resolve("continue_hierarchical_skill")),
    "request_skill_repair": _wrap(_resolve("request_skill_repair")),

    # ---------------- Qora adapters (graph/WM/etc.) ----------------
    "qora_wm_reindex_changed": _wrap(_resolve("qora_wm_reindex_changed")),
    "qora_wm_search": _wrap(_resolve("qora_wm_search")),
    "qora_annotate_diff": _wrap(_resolve("qora_annotate_diff")),
    "qora_policy_check_diff": _wrap(_resolve("qora_policy_check_diff")),
    "qora_recipe_write": _wrap(_resolve("qora_recipe_write")),
    "qora_recipe_find": _wrap(_resolve("qora_recipe_find")),
    "qora_impact_plan": _wrap(_resolve("qora_impact_plan")),
    "qora_mutation_estimate": _wrap(_resolve("qora_mutation_estimate")),
    "qora_mutation_run": _wrap(_resolve("qora_mutation_run")),
    "qora_spec_eval_run": _wrap(_resolve("qora_spec_eval_run")),
    "qora_secrets_scan": _wrap(_resolve("qora_secrets_scan")),
    "qora_rg_search": _wrap(_resolve("qora_rg_search")),
    "qora_catalog_list": _wrap(_resolve("qora_catalog_list")),
    "qora_catalog_get": _wrap(_resolve("qora_catalog_get")),
    "qora_catalog_register": _wrap(_resolve("qora_catalog_register")),
    "qora_catalog_retire": _wrap(_resolve("qora_catalog_retire")),
    "qora_shadow_run": _wrap(_resolve("qora_shadow_run")),
    "qora_auto_pipeline": _wrap(_resolve("qora_auto_pipeline")),
    "qora_git_branch_from_diff": _wrap(_resolve("qora_git_branch_from_diff")),
    "qora_git_rollback": _wrap(_resolve("qora_git_rollback")),
    "qora_gh_open_pr": _wrap(_resolve("qora_gh_open_pr")),
}
