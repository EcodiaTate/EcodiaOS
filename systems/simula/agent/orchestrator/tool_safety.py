# systems/simula/agent/orchestrator/tool_safety.py
# --- AMBITIOUS UPGRADE (ADDED NEW TOOLS FOR QORA & NOVA) ---
from __future__ import annotations
import inspect
from collections.abc import Awaitable, Callable
from typing import Any
from systems.simula.agent import qora_adapters as _qora
from systems.simula.nscs import agent_tools as _nscs
from systems.simula.agent import nova_adapters as _nova 

def _wrap(func: Callable[..., Any]) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    sig = inspect.signature(func)
    is_async = inspect.iscoroutinefunction(func)
    params_list = list(sig.parameters.values())
    call_as_params_dict = len(params_list) == 1 and params_list[0].name in {"params", "payload"} 
    async def runner(params: dict[str, Any]) -> dict[str, Any]:
        params = params or {}
        call = func(params) if call_as_params_dict else func(**params)
        return await call if is_async else call
    return runner

TOOLS: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    # === Core Agent Capabilities ===
    "propose_intelligent_patch": _wrap(_nscs.propose_intelligent_patch),
    "get_context_dossier": _wrap(_nscs.get_context_dossier),
    "commit_plan_to_memory": _wrap(_nscs.commit_plan_to_memory),
    
    # === NEW: Advanced Reasoning & Learning Tools ===
    "qora_request_critique": _wrap(_qora.request_critique),
    "qora_find_similar_failures": _wrap(_qora.find_similar_failures),
    "qora_find_similar_code": _wrap(_nscs.qora_find_similar_code),
    "qora_get_call_graph": _wrap(_nscs.qora_get_call_graph),
    "qora_get_goal_context": _wrap(_qora.qora_get_goal_context), # NEW
    "reindex_code_graph": _wrap(_qora.qora_reindex_code_graph),
    "nova_propose_and_auction": _wrap(_nova.propose_and_auction), # NEW

    # === Filesystem & Code Operations ===
    "list_files": _wrap(_nscs.list_files),
    "file_search": _wrap(_nscs.file_search),
    "read_file": _wrap(_nscs.read_file),
    "write_code": _wrap(_nscs.write_file),
    "delete_file": _wrap(_nscs.delete_file),
    "rename_file": _wrap(_nscs.rename_file),
    "create_directory": _wrap(_nscs.create_directory),
    "apply_refactor": _wrap(_nscs.apply_refactor),
    "apply_refactor_smart": _wrap(_nscs.apply_refactor_smart),

    # === Quality, Testing & Hygiene ===
    "generate_tests": _wrap(_nscs.generate_tests),
    "generate_property_test": _wrap(_nscs.generate_property_test),
    "run_tests": _wrap(_nscs.run_tests),
    "run_tests_k": _wrap(_nscs.run_tests_k),
    "run_tests_xdist": _wrap(_nscs.run_tests_xdist),
    "run_tests_and_diagnose_failures": _wrap(_nscs.run_tests_and_diagnose_failures),
    "static_check": _wrap(_nscs.static_check),
    "run_repair_engine": _wrap(_nscs.run_repair_engine),
    "run_fuzz_smoke": _wrap(_nscs.run_fuzz_smoke),
    "format_patch": _wrap(_nscs.format_patch),
    "qora_hygiene_check": _wrap(_qora.qora_hygiene_check),
    
    # === VCS, CI/CD & Deployment ===
    "open_pr": _wrap(_nscs.open_pr),
    "rebase_patch": _wrap(_nscs.rebase_patch),
    "conventional_commit_title": _wrap(_nscs.conventional_commit_title),
    "conventional_commit_message": _wrap(_nscs.conventional_commit_message), 
    "render_ci_yaml": _wrap(_nscs.render_ci_yaml),
    "run_ci_locally": _wrap(_nscs.run_ci_locally),
    "run_system_simulation": _wrap(_nscs.run_system_simulation),

    # === Qora Service Adapters (General) ===
    "qora_impact_plan": _wrap(_qora.qora_impact_plan),
    "qora_policy_check_diff": _wrap(_qora.qora_policy_check_diff),
    "qora_shadow_run": _wrap(_qora.qora_shadow_run),
    "qora_bb_write": _wrap(_qora.qora_bb_write),
    "qora_bb_read": _wrap(_qora.qora_bb_read),
    "qora_proposal_bundle": _wrap(_qora.qora_proposal_bundle),
    "qora_secrets_scan": _wrap(_qora.qora_secrets_scan),
    "qora_spec_eval_run": _wrap(_qora.qora_spec_eval_run),
    "package_artifacts": _wrap(_nscs.package_artifacts),
    "record_recipe": _wrap(_nscs.record_recipe),
}