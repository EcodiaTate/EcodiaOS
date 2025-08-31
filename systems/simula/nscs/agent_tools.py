# systems/simula/nscs/agent_tools.py
# --- FULL FIXED FILE ---
from __future__ import annotations

import ast
import codecs
from pathlib import Path
from typing import Any
import json
import re
import uuid

# Wrappers for advanced tools
from systems.simula.agent import tools_advanced as _adv
from systems.simula.agent import tools_extra as _extra

# Sentinel-upgraded modules
from systems.simula.agent.strategies.apply_refactor_smart import (
    apply_refactor_smart as _apply_refactor_smart,
)
from systems.qora import api_client as qora_client
from systems.simula.code_sim.fuzz.hypo_driver import run_hypothesis_smoke
from systems.simula.code_sim.repair.engine import attempt_repair
from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import ensure_toolchain, seed_config
from systems.simula.code_sim.telemetry import track_tool
from systems.simula.config import settings
from core.prompting.orchestrator import PolicyHint, build_prompt
from core.utils.net_api import get_http_client
from systems.simula.code_sim.diagnostics.error_parser import parse_pytest_output
from systems.simula.code_sim.evaluators.spec_miner import derive_acceptance
from systems.simula.nscs.twin.runner import run_scenarios

# -----------------------------------------------------------------------------
# Shared Helpers
# -----------------------------------------------------------------------------


def _normalize_paths(paths: list[str] | None) -> list[str]:
    """Provides a default path if none are given."""
    if not paths:
        return ["."]
    return [p for p in paths if p]

# -----------------------------------------------------------------------------
# Code & File Operations
# -----------------------------------------------------------------------------


@track_tool("write_code")
async def write_file(*, path: str, content: str, append: bool = False) -> dict[str, Any]:
    """Safely writes content to a file within the repository root."""
    p = Path(path)
    if p.is_absolute():
        return {"status": "error", "reason": "Absolute paths are disallowed."}
    abs_p = (Path(settings.repo_root) / p).resolve()
    if settings.repo_root not in str(abs_p):
        return {"status": "error", "reason": "Path traversal outside of repo root is disallowed."}
    try:
        decoded_content = codecs.decode(content, "unicode_escape")
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with abs_p.open(mode, encoding="utf-8", newline="\n") as f:
            f.write(decoded_content)
        rel_path = str(abs_p.relative_to(settings.repo_root))
        return {"status": "success", "result": {"path": rel_path}}
    except Exception as e:
        return {"status": "error", "reason": f"File operation failed: {e!r}"}


@track_tool("read_file")
async def read_file(*, path: str) -> dict[str, Any]:
    """Safely reads the content of a file within the repository root."""
    p = Path(path)
    if p.is_absolute():
        return {"status": "error", "reason": "Absolute paths are disallowed."}
    abs_p = (Path(settings.repo_root) / p).resolve()
    if settings.repo_root not in str(abs_p):
        return {"status": "error", "reason": "Path traversal outside of repo root is disallowed."}
    
    try:
        if not abs_p.is_file():
            return {"status": "error", "reason": f"File not found at: {path}"}
        
        content = abs_p.read_text(encoding="utf-8")
        rel_path = str(abs_p.relative_to(settings.repo_root))
        return {"status": "success", "result": {"path": rel_path, "content": content}}
    except Exception as e:
        return {"status": "error", "reason": f"File read operation failed: {e!r}"}


@track_tool("list_files")
async def list_files(*, path: str = ".", recursive: bool = False, max_depth: int = 3) -> dict[str, Any]:
    """Lists files and directories at a given path within the repository using the sandbox."""
    cfg = seed_config()
    
    # Use the 'find' command for robust, sandboxed file listing.
    if recursive:
        cmd = ["find", path, "-maxdepth", str(max_depth)]
    else:
        cmd = ["find", path, "-maxdepth", "1"]
        
    async with DockerSandbox(cfg).session() as sess:
        out = await sess._run_tool(cmd, timeout=60)

    if out.get("returncode", 1) != 0:
        return {"status": "error", "reason": out.get("stderr") or out.get("stdout", "List files command failed.")}
    
    found_items = out.get("stdout", "").strip().splitlines()
    # The output of find includes the path itself; remove it for a cleaner result.
    if path in found_items:
        found_items.remove(path)

    return {"status": "success", "result": {"items": sorted(found_items[:2000])}}


@track_tool("file_search")
async def file_search(*, pattern: str, path: str = ".") -> dict[str, Any]:
    """Searches for a regex pattern within files in the repository (like 'grep')."""
    cfg = seed_config()
    search_path = "/workspace" # Always search from the root of the mounted workspace
    cmd = ["grep", "-r", "-l", "-E", pattern, search_path]
    
    async with DockerSandbox(cfg).session() as sess:
        out = await sess._run_tool(cmd, timeout=120)

    # Grep returns 1 if not found, which is not an error.
    if out.get("returncode", 1) > 1:
        return {"status": "error", "reason": out.get("stderr") or out.get("stdout", "Search command failed.")}
    
    found_files = out.get("stdout", "").strip().splitlines()
    repo_relative_paths = [f".{p.replace('/workspace', '')}" for p in found_files]
    
    return {"status": "success", "result": {"matches": repo_relative_paths}}


@track_tool("delete_file")
async def delete_file(*, path: str) -> dict[str, Any]:
    """Deletes a file within the repository."""
    if ".." in path:
        return {"status": "error", "reason": "Path traversal ('..') is disallowed."}
    p = (Path(settings.repo_root) / path).resolve()
    if settings.repo_root not in str(p):
        return {"status": "error", "reason": "Path is outside the repository root."}
    
    try:
        if not p.is_file():
            return {"status": "error", "reason": f"Not a file or does not exist: {path}"}
        p.unlink()
        return {"status": "success", "result": {"path": path}}
    except Exception as e:
        return {"status": "error", "reason": f"File deletion failed: {e!r}"}


@track_tool("rename_file")
async def rename_file(*, source_path: str, destination_path: str) -> dict[str, Any]:
    """Renames or moves a file or directory."""
    if ".." in source_path or ".." in destination_path:
        return {"status": "error", "reason": "Path traversal ('..') is disallowed."}
    
    source_p = (Path(settings.repo_root) / source_path).resolve()
    dest_p = (Path(settings.repo_root) / destination_path).resolve()

    if settings.repo_root not in str(source_p) or settings.repo_root not in str(dest_p):
        return {"status": "error", "reason": "Paths must be within the repository root."}
    
    try:
        if not source_p.exists():
            return {"status": "error", "reason": f"Source path does not exist: {source_path}"}
        dest_p.parent.mkdir(parents=True, exist_ok=True)
        source_p.rename(dest_p)
        return {"status": "success", "result": {"from": source_path, "to": destination_path}}
    except Exception as e:
        return {"status": "error", "reason": f"File rename/move failed: {e!r}"}


@track_tool("create_directory")
async def create_directory(*, path: str) -> dict[str, Any]:
    """Creates a new directory (including any necessary parent directories)."""
    if ".." in path:
        return {"status": "error", "reason": "Path traversal ('..') is disallowed."}
    p = (Path(settings.repo_root) / path).resolve()
    if settings.repo_root not in str(p):
        return {"status": "error", "reason": "Path is outside the repository root."}
        
    try:
        p.mkdir(parents=True, exist_ok=True)
        return {"status": "success", "result": {"path": path}}
    except Exception as e:
        return {"status": "error", "reason": f"Directory creation failed: {e!r}"}


@track_tool("apply_refactor")
async def apply_refactor(*, diff: str, verify_paths: list[str] | None = None) -> dict[str, Any]:
    """Applies a diff and runs tests in the sandbox, returning structured results."""
    paths_to_verify = _normalize_paths(verify_paths or ["tests"])
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ok_apply = await sess.apply_unified_diff(diff)
        if not ok_apply:
            return {
                "status": "error",
                "reason": "Failed to apply patch.",
                "logs": "git apply failed",
            }
        ok_tests, logs = await sess.run_pytest(paths_to_verify)
        return {
            "status": "success" if ok_tests else "failed",
            "result": {"passed": ok_tests, "logs": logs},
        }


@track_tool("apply_refactor_smart")
async def apply_refactor_smart(
    *,
    diff: str,
    verify_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Applies a diff in chunks, testing after each chunk."""
    return await _apply_refactor_smart(diff, verify_paths=_normalize_paths(verify_paths))


# -----------------------------------------------------------------------------
# Quality & Hygiene Tools
# -----------------------------------------------------------------------------

def _discover_functions_from_source(src: str) -> list[str]:
    """Safely parses Python source and extracts top-level function names."""
    names: list[str] = []
    try:
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(
                node,
                ast.FunctionDef | ast.AsyncFunctionDef,
            ) and not node.name.startswith("_"):
                names.append(node.name)
    except Exception:
        pass
    return names


@track_tool("generate_tests")
async def generate_tests(*, module: str) -> dict[str, Any]:
    """Generates a skeleton pytest file for a given Python module to improve coverage."""
    target_path = Path(settings.repo_root) / module
    if not target_path.exists():
        return {"status": "error", "reason": f"Module not found: {module}"}
    source_code = target_path.read_text(encoding="utf-8")
    function_names = _discover_functions_from_source(source_code)
    test_dir = Path(settings.repo_root) / "tests"
    test_dir.mkdir(exist_ok=True)
    test_path = test_dir / f"test_{target_path.stem}.py"
    if test_path.exists():
        return {"status": "noop", "reason": f"Test file already exists at {test_path}"}
    module_import_path = module.replace(".py", "").replace("/", ".")
    content = [
        f'"""Auto-generated skeleton tests for {module}."""',
        "import pytest",
        f"from {module_import_path} import *",
        "",
    ]
    if not function_names:
        content.extend(
            [
                "def test_module_import():",
                f'    """Verify that {module} can be imported."""',
                "    assert True",
            ],
        )
    else:
        for name in function_names:
            content.extend(
                [
                    f"def test_{name}_smoke():",
                    f'    """A smoke test for the function {name}."""',
                    "    pytest.skip('Not yet implemented')",
                    "",
                ],
            )
    full_content = "\n".join(content)
    return {
        "status": "success",
        "result": {
            "proposal_type": "new_file",
            "path": str(test_path.relative_to(settings.repo_root)),
            "content": full_content,
        },
    }

@track_tool("run_tests")
async def run_tests(*, paths: list[str], timeout_sec: int = 900) -> dict[str, Any]:
    paths = _normalize_paths(paths)
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ok, logs = await sess.run_pytest(paths, timeout=timeout_sec)
        return {"status": "success" if ok else "failed", "result": {"passed": ok, "logs": logs}}


@track_tool("run_tests_k")
async def run_tests_k(*, paths: list[str], k_expr: str, timeout_sec: int = 600) -> dict[str, Any]:
    paths = _normalize_paths(paths)
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ok, logs = await sess.run_pytest_select(paths, k_expr=k_expr, timeout=timeout_sec)
        return {"status": "success" if ok else "failed", "result": {"passed": ok, "logs": logs}}


@track_tool("run_tests_xdist")
async def run_tests_xdist(
    *,
    paths: list[str] | None = None,
    nprocs: str | int = "auto",
    timeout_sec: int = 900,
) -> dict[str, Any]:
    paths = _normalize_paths(paths or ["tests"])
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ok, logs = await sess.run_pytest_xdist(paths, nprocs=nprocs, timeout=timeout_sec)
        return {"status": "success" if ok else "failed", "result": {"passed": ok, "logs": logs}}


@track_tool("static_check")
async def static_check(*, paths: list[str]) -> dict[str, Any]:
    paths = _normalize_paths(paths)
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ruff_out = await sess.run_ruff(paths)
        mypy_out = await sess.run_mypy(paths)
        ruff_ok = ruff_out.get("returncode", 1) == 0
        mypy_ok = mypy_out.get("returncode", 1) == 0
        return {
            "status": "success" if ruff_ok and mypy_ok else "failed",
            "result": {"ruff_ok": ruff_ok, "mypy_ok": mypy_ok, "ruff": ruff_out, "mypy": mypy_out},
        }


@track_tool("run_repair_engine")
async def run_repair_engine(*, paths: list[str], timeout_sec: int = 600) -> dict[str, Any]:
    out = await attempt_repair(_normalize_paths(paths), timeout_sec=timeout_sec)
    return {
        "status": out.status,
        "result": {"diff": out.diff, "tried": out.tried, "notes": out.notes},
    }


@track_tool("run_fuzz_smoke")
async def run_fuzz_smoke(*, module: str, function: str, timeout_sec: int = 600) -> dict[str, Any]:
    ok, logs = await run_hypothesis_smoke(module, function, timeout_sec=timeout_sec)
    return {"status": "success" if ok else "failed", "result": {"passed": ok, "logs": logs}}


# --- Meta-Tool Implementations ---

@track_tool("propose_intelligent_patch")
async def propose_intelligent_patch(*, goal: str, objective: dict) -> dict[str, Any]:
    """A placeholder to be handled by the orchestrator's _call_tool method."""
    return {"status": "pending_orchestrator_hook", "goal": goal, "objective": objective}


@track_tool("commit_plan_to_memory")
async def commit_plan_to_memory(*, plan: list[str], thoughts: str) -> dict[str, Any]:
    """A placeholder to be handled by the orchestrator's _call_tool method."""
    return {"status": "pending_orchestrator_hook", "plan": plan, "thoughts": thoughts}

@track_tool("create_plan")
async def create_plan(*, goal: str) -> dict[str, Any]:
    """
    Takes a high-level goal and generates a structured, multi-step plan
    for the agent to execute. This is the first step in strategic execution.
    """
    try:
        hint = PolicyHint(scope="simula.plan.create", context={"vars": {"goal": goal}})
        prompt_data = await build_prompt(hint)
        http = await get_http_client()
        payload = {"agent_name": "SimulaPlanner", "messages": prompt_data.messages, "provider_overrides": {"json_mode": True, **prompt_data.provider_overrides}}
        resp = await http.post("/llm/call", json=payload, timeout=120)
        resp.raise_for_status()
        body = resp.json()
        plan_json = body.get("json", {}) if isinstance(body.get("json"), dict) else json.loads(body.get("text", "{}"))
        if "plan" not in plan_json:
            return {"status": "error", "reason": "LLM failed to generate a valid plan structure."}
        return {"status": "success", "result": {"plan": plan_json["plan"]}}
    except Exception as e:
        return {"status": "error", "reason": f"Failed to create plan: {e!r}"}

@track_tool("request_plan_repair")
async def request_plan_repair(*, original_plan: list[str], failed_step: str, error_context: str) -> dict[str, Any]:
    """
    When a step in a plan fails, this tool asks an LLM to generate a revised plan.
    This enables robust, self-correcting strategic execution.
    """
    try:
        context = {
            "vars": {
                "original_plan": original_plan,
                "failed_step": failed_step,
                "error_context": error_context,
            }
        }
        hint = PolicyHint(scope="simula.plan.repair", context=context)
        prompt_data = await build_prompt(hint)
        http = await get_http_client()
        payload = {"agent_name": "SimulaRepair", "messages": prompt_data.messages, "provider_overrides": {"json_mode": True, **prompt_data.provider_overrides}}
        resp = await http.post("/llm/call", json=payload, timeout=120)
        resp.raise_for_status()
        body = resp.json()
        repaired_plan = body.get("json", {}) if isinstance(body.get("json"), dict) else json.loads(body.get("text", "{}"))
        if "repaired_plan" not in repaired_plan:
            return {"status": "error", "reason": "LLM failed to generate a repaired plan."}
        return {"status": "success", "result": {"repaired_plan": repaired_plan["repaired_plan"]}}
    except Exception as e:
        return {"status": "error", "reason": f"Failed to repair plan: {e!r}"}


@track_tool("propose_new_system_tool")
async def propose_new_system_tool(*, goal: str, rationale: str) -> dict[str, Any]:
    """
    AUTONOMOUS SELF-IMPROVEMENT: Generates the Python code for a new tool,
    complete with an @eos_tool decorator, and writes it to a file for Qora to ingest.
    """
    try:
        context = {"vars": {"goal": goal, "rationale": rationale}}
        hint = PolicyHint(scope="simula.toolgen.propose", context=context)
        prompt_data = await build_prompt(hint)
        http = await get_http_client()
        payload = {"agent_name": "SimulaToolgen", "messages": prompt_data.messages, "provider_overrides": prompt_data.provider_overrides}
        resp = await http.post("/llm/call", json=payload, timeout=180)
        resp.raise_for_status()
        body = resp.json()
        
        raw_code = body.get("text", "")
        clean_code = _strip_markdown_fences(raw_code)

        if "def " not in clean_code or "@" not in clean_code:
            return {"status": "error", "reason": "LLM failed to generate valid tool code."}

        # Extract function name for filename
        match = re.search(r"def\s+(\w+)\s*\(", clean_code)
        func_name = match.group(1) if match else f"new_tool_{uuid.uuid4().hex[:6]}"
        
        # Write to a designated file for auto-discovery
        tool_file_path = Path(settings.repo_root) / "systems/simula/agent/tools_generated.py"
        
        # Ensure file exists and append the new tool
        current_content = ""
        if tool_file_path.exists():
            current_content = tool_file_path.read_text(encoding="utf-8")
        
        new_content = current_content + "\n\n" + clean_code + "\n"
        
        await write_file(path=str(tool_file_path.relative_to(settings.repo_root)), content=new_content)

        return {
            "status": "success",
            "result": {
                "tool_name": func_name,
                "file_path": str(tool_file_path.relative_to(settings.repo_root)),
                "next_step": "Recommend calling 'reindex_code_graph' to make the tool available."
            }
        }
    except Exception as e:
        return {"status": "error", "reason": f"Failed to propose new tool: {e!r}"}

# --- GOD-LEVEL VERIFICATION ---
@track_tool("run_system_simulation")
async def run_system_simulation(*, diff: str, scenarios: list[str] | None = None) -> dict[str, Any]:
    """
    The ultimate verification step. Applies a change to a 'digital twin' of the
    entire system and runs realistic end-to-end scenarios to check for unintended
    consequences, performance regressions, or system-level failures.
    """
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        ok_apply = await sess.apply_unified_diff(diff)
        if not ok_apply:
            return {"status": "error", "reason": "Failed to apply diff in simulation environment."}
        
        sim_scenarios = scenarios or [{"name": "smoke", "type": "http", "requests": 10}]
        # The run_scenarios function would contain logic to execute complex tests
        # (e.g., using docker-compose, running load tests, checking database state).
        sim_results = run_scenarios(sim_scenarios)

    return {"status": "success", "result": sim_results}

def _strip_markdown_fences(text: str) -> str:
    """Removes Python markdown fences from LLM output."""
    match = re.search(r"```python\n(.*)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


@track_tool("generate_property_test")
async def generate_property_test(*, file_path: str, function_signature: str) -> dict[str, Any]:
    """Generates a property-based test for a given function to find edge cases."""
    try:
        hint = PolicyHint(
            scope="simula.testgen.property",
            context={
                "vars": {
                    "file_path": file_path,
                    "function_signature": function_signature
                }
            }
        )
        prompt_data = await build_prompt(hint)
        http = await get_http_client()
        payload = {
            "agent_name": "SimulaTestGen",
            "messages": prompt_data.messages,
            "provider_overrides": prompt_data.provider_overrides,
        }
        resp = await http.post("/llm/call", json=payload, timeout=120)
        resp.raise_for_status()
        body = resp.json()
        
        raw_code = body.get("text", "")
        clean_code = _strip_markdown_fences(raw_code)

        if not clean_code:
            return {"status": "error", "reason": "LLM failed to generate test code."}

        func_name = function_signature.split("(")[0].strip()
        test_file_path = f"tests/property/test_prop_{func_name}_{uuid.uuid4().hex[:6]}.py"
        
        return {
            "status": "success",
            "result": {
                "proposal_type": "new_file",
                "path": test_file_path,
                "content": clean_code,
            },
        }
    except Exception as e:
        return {"status": "error", "reason": f"Failed to generate property test: {e!r}"}


@track_tool("get_context_dossier")
async def get_context_dossier(*, target_fqname: str, intent: str) -> dict[str, Any]:
    """
    Builds a rich dossier by calling the central Qora World Model service.
    """
    try:
        qora_response = await qora_client.get_dossier(target_fqname=target_fqname, intent=intent)
        return {"status": "success", "result": {"dossier": qora_response}}
    except Exception as e:
        return {"status": "error", "reason": f"Dossier service call failed: {e!r}"}


@track_tool("qora_find_similar_code")
async def qora_find_similar_code(*, query_text: str, top_k: int = 5) -> dict[str, Any]:
    """
    Finds functions or classes that are semantically similar to the query text.
    """
    try:
        search_results = await qora_client.semantic_search(query_text=query_text, top_k=top_k)
        return {"status": "success", "result": {"hits": search_results}}
    except Exception as e:
        return {"status": "error", "reason": f"Semantic code search failed: {e!r}"}


@track_tool("qora_get_call_graph")
async def qora_get_call_graph(*, target_fqn: str) -> dict[str, Any]:
    """
    Retrieves the direct callers and callees for a specific function from the Code Graph.
    """
    try:
        graph_data = await qora_client.get_call_graph(target_fqn=target_fqn)
        return {"status": "success", "result": graph_data}
    except Exception as e:
        return {"status": "error", "reason": f"Call graph retrieval failed: {e!r}"}


@track_tool("run_tests_and_diagnose_failures")
async def run_tests_and_diagnose_failures(*, paths: list[str] | None = None, k_expr: str = "") -> dict[str, Any]:
    """
    Runs tests and, if they fail, analyzes the output to find the root cause
    and suggest a specific fix.
    """
    paths_to_test = _normalize_paths(paths)
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ok, logs = await sess.run_pytest_select(paths_to_test, k_expr=k_expr, timeout=900)

    stdout = logs.get("stdout", "")
    if ok:
        return {"status": "success", "result": {"passed": True, "logs": logs}}

    try:
        failures = parse_pytest_output(stdout)
        acceptance_hints = derive_acceptance(stdout)
        return {
            "status": "failed",
            "result": {
                "passed": False,
                "logs": logs,
                "diagnostics": {
                    "parsed_failures": [f.__dict__ for f in failures],
                    "repair_suggestions": acceptance_hints.get("acceptance_hints", []),
                }
            }
        }
    except Exception as e:
        return {"status": "error", "reason": f"Test diagnostics failed: {e!r}", "logs": logs}


@track_tool("run_system_simulation")
async def run_system_simulation(*, diff: str, scenarios: list[str] | None = None) -> dict[str, Any]:
    """
    Applies a diff in a 'digital twin' environment and runs integration scenarios.
    """
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        ok_apply = await sess.apply_unified_diff(diff)
        if not ok_apply:
            return {"status": "error", "reason": "Failed to apply diff in simulation environment."}
        
        sim_scenarios = scenarios or [{"name": "smoke", "type": "http", "requests": 10}]
        sim_results = run_scenarios(sim_scenarios)

    return {"status": "success", "result": sim_results}


# -----------------------------------------------------------------------------
# VCS, Policy & Artifact Tools (Wrappers around advanced/extra tools)
# -----------------------------------------------------------------------------

@track_tool("open_pr")
async def open_pr(
    *,
    diff: str,
    title: str,
    evidence: dict | None = None,
    base: str = "main",
) -> dict:
    return await _extra.tool_open_pr(
        {"diff": diff, "title": title, "evidence": evidence or {}, "base": base},
    )


@track_tool("package_artifacts")
async def package_artifacts(
    *,
    proposal_id: str,
    evidence: dict,
    extra_paths: list[str] | None = None,
) -> dict:
    return await _extra.tool_package_artifacts(
        {"proposal_id": proposal_id, "evidence": evidence, "extra_paths": (extra_paths or [])},
    )


@track_tool("policy_gate")
async def policy_gate(*, diff: str) -> dict:
    return await _extra.tool_policy_gate({"diff": diff})


@track_tool("impact_and_cov")
async def impact_and_cov(*, diff: str) -> dict:
    return await _extra.tool_impact_cov({"diff": diff})


@track_tool("format_patch")
async def format_patch(*, paths: list[str]) -> dict:
    return await _adv.format_patch({"paths": _normalize_paths(paths)})


@track_tool("rebase_patch")
async def rebase_patch(*, diff: str, base: str = "origin/main") -> dict:
    return await _adv.rebase_patch({"diff": diff, "base": base})


@track_tool("conventional_commit_title")
async def conventional_commit_title(*, evidence: dict) -> dict:
    return await _extra.tool_commit_title({"evidence": evidence})


@track_tool("conventional_commit_message")
async def conventional_commit_message(
    *,
    type: str,
    scope: str | None,
    subject: str,
    body: str | None,
) -> dict:
    return await _extra.tool_conventional_commit(
        {"type": type, "scope": scope, "subject": subject, "body": body}
    )


@track_tool("render_ci_yaml")
async def render_ci_yaml(*, provider: str = "github", use_xdist: bool = True) -> dict:
    return await _extra.tool_render_ci({"provider": provider, "use_xdist": use_xdist})


@track_tool("record_recipe")
async def record_recipe(**kwargs) -> dict:
    return await _adv.record_recipe(kwargs)


@track_tool("run_ci_locally")
async def run_ci_locally(*, paths: list[str] | None = None, timeout_sec: int = 2400) -> dict:
    return await _adv.run_ci_locally({"paths": paths, "timeout_sec": timeout_sec})