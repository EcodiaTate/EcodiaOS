# systems/simula/nscs/agent_tools.py
# --- DEFINITIVE, CONSOLIDATED, AND FULLY REFACTORED IMPLEMENTATION ---
# This file is the single source of truth for all of Simula's tool implementations.

from __future__ import annotations

import ast
import io
import json
import logging
import os
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from github import Github

# --- Core EcodiaOS/Simula Imports ---
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service, extract_json_flex
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.nova.schemas import AuctionResult, InnovationBrief, InventionCandidate
from systems.qora import api_client as qora_client
from systems.simula.artifacts.package import create_artifact_bundle
from systems.simula.build.run import run_build_and_tests
from systems.simula.ci.pipelines import render_ci
from systems.simula.code_sim.diagnostics.error_parser import parse_pytest_output
from systems.simula.code_sim.fuzz.hypo_driver import run_hypothesis_smoke
from systems.simula.code_sim.repair.engine import attempt_repair
from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import ensure_toolchain, seed_config
from systems.simula.code_sim.telemetry import track_tool
from systems.simula.format.autoformat import autoformat_changed
from systems.simula.git.rebase import rebase_diff_onto_branch
from systems.simula.ops.glue import quick_impact_and_cov, quick_policy_gate
from systems.simula.recipes.generator import append_recipe
from systems.simula.search.portfolio_runner import rank_portfolio
from systems.simula.vcs.commit_msg import render_conventional_commit, title_from_evidence
from systems.simula.vcs.pr_manager import open_pr as _open_pr_impl

from .evolution import execute_code_evolution

log = logging.getLogger(__name__)

# ==============================================================================
# SECTION: Shared Helpers
# ==============================================================================


def _normalize_paths(paths: list[str] | None) -> list[str]:
    """Provides a default path if none are given and filters empty strings."""
    return [p for p in (paths or ["."]) if p]


def _strip_markdown_fences(text: str) -> str:
    """Removes typical markdown/code fences from LLM output."""
    if not isinstance(text, str):
        return ""
    match = re.search(r"```(?:[a-zA-Z0-9]*)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


# --- Registry helpers for bootstrap -----------------------------------------
from systems.simula.code_sim.telemetry import get_tracked_tools as _get_tracked_tools


def get_all_tool_arm_ids() -> list[str]:
    """
    Return fully-qualified PolicyArm IDs for every tracked Simula tool.
    Used by the registry bootstrapper to compute the expected-ID set.
    """
    try:
        tools = _get_tracked_tools() or {}
        return [f"simula.agent.tools.{name}" for name in tools.keys()]
    except Exception as e:
        log.error("get_all_tool_arm_ids failed: %r", e, exc_info=True)
        return []


def _discover_functions(src: str) -> list[str]:
    """Parses source code to find top-level function definitions."""
    names: list[str] = []
    try:
        tree = ast.parse(src)
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
                names.append(n.name)
    except Exception:
        pass
    return names


async def _api_call(
    method: str,
    endpoint_name: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """A single, robust helper for making API calls to internal services."""
    try:
        http = await get_http_client()
        url = getattr(ENDPOINTS, endpoint_name)
        if method.upper() == "POST":
            response = await http.post(url, json=payload or {}, timeout=timeout)
        elif method.upper() == "GET":
            response = await http.get(url, params=payload or {}, timeout=timeout)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        response.raise_for_status()
        return {"status": "success", "result": response.json() or {}}
    except AttributeError:
        return {"status": "error", "reason": f"Config error: Endpoint '{endpoint_name}' not found."}
    except Exception as e:
        return {"status": "error", "reason": f"API call to '{endpoint_name}' failed: {e!r}"}


async def _post(path: str, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    http = await get_http_client()
    r = await http.post(path, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}


async def _get(path: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    http = await get_http_client()
    r = await http.get(path, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}


async def _bb_write(key: str, value: Any) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_BB_WRITE", "/qora/bb/write")
    return await _post(url, {"key": key, "value": value})


async def _bb_read(key: str) -> Any:
    url = getattr(ENDPOINTS, "QORA_BB_READ", "/qora/bb/read")
    out = await _get(url, {"key": key})
    return out.get("value") if isinstance(out, dict) else out


# ==============================================================================
# SECTION: High-Level / Meta Tools
# ==============================================================================


@track_tool("propose_intelligent_patch", modes=["simula_planful", "planning", "code_generation"])
async def propose_intelligent_patch(*, goal: str, objective: dict) -> dict[str, Any]:
    """
    Triggers the full, self-contained, multi-step code evolution engine.

    This is a powerful, high-level tool that autonomously attempts to solve a complex
    coding task. Use this for broad goals like 'implement feature X' or 'refactor module Y'
    that require planning, code generation, and verification.

    Args:
        goal: The high-level objective for the code evolution.
        objective: A structured dictionary providing more specific details or constraints.
    """
    return await execute_code_evolution(goal=goal, objective=objective)


@track_tool(
    "edit_code_block",
    modes=["simula_planful", "code_generation", "refactoring", "debugging"],
)
async def edit_code_block(
    *,
    file_path: str,
    block_identifier: str,
    new_code_block: str,
) -> dict[str, Any]:
    """
    Surgically replaces a block of code within a file without rewriting the entire file.

    This is a high-precision tool for refactoring, fixing, or replacing a single function,
    class, or method. It identifies the target block using a unique starting line (the identifier)
    and replaces it while preserving indentation. It is strongly preferred over `write_file`
    for any modification that doesn't involve creating a new file.

    Args:
        file_path: The relative path to the file that needs to be modified.
        block_identifier: A unique line of code that marks the beginning of the block
                          to be replaced (e.g., "def my_function(arg1):" or "class MyClass:").
                          This line MUST be present in the file.
        new_code_block: The new block of code that will replace the old one.
    """
    # Step 1: Read the existing file content using the dedicated tool.
    read_result = await read_file(path=file_path)
    if read_result.get("status") != "success":
        return {
            "status": "error",
            "reason": f"Failed to read file for editing: {read_result.get('reason')}",
        }

    original_content = read_result.get("result", {}).get("content", "")
    lines = original_content.splitlines()

    # Step 2: Find the block to replace using the identifier.
    start_line_index = -1
    block_indentation = ""
    for i, line in enumerate(lines):
        if block_identifier in line:
            start_line_index = i
            # Capture the indentation of the block's first line.
            match = re.match(r"^(\s*)", line)
            if match:
                block_indentation = match.group(1)
            break

    if start_line_index == -1:
        return {
            "status": "error",
            "reason": f"Block identifier not found in file: '{block_identifier}'",
        }

    # Step 3: Find the end of the block based on indentation.
    end_line_index = start_line_index
    for i in range(start_line_index + 1, len(lines)):
        line = lines[i]
        # A block ends when a line is not empty and has indentation less than or equal to the starting line's.
        if line.strip() and (len(line) - len(line.lstrip(" "))) <= len(block_indentation):
            break
        end_line_index = i

    # Step 4: Prepare the new code block with correct indentation.
    dedented_new_block = textwrap.dedent(new_code_block).strip()
    new_lines = [f"{block_indentation}{line}" for line in dedented_new_block.splitlines()]

    # Step 5: Reconstruct the file content.
    final_lines = (
        lines[:start_line_index]  # All lines before the block.
        + new_lines  # The new, correctly indented block.
        + lines[end_line_index + 1 :]  # All lines after the block.
    )
    final_content = "\n".join(final_lines)

    # Step 6: Write the modified content back to the file.
    write_result = await write_file(path=file_path, content=final_content)
    if write_result.get("status") != "success":
        return {
            "status": "error",
            "reason": f"Failed to write file after editing: {write_result.get('reason')}",
        }

    return {
        "status": "success",
        "result": {
            "path": file_path,
            "notes": f"Successfully replaced block identified by '{block_identifier}'.",
        },
    }


@track_tool("ask_senior_architect", modes=["simula_planful", "reasoning", "planning"])
async def ask_senior_architect(*, question: str, context: str) -> dict[str, Any]:
    """
    Asks a high-level, conceptual question about software design, best practices, or architectural
    patterns to a simulated senior architect. Use this for advice, not for code generation.

    This tool is for gaining understanding before acting. Use it to clarify doubts about
    the best approach, understand risks, or learn about existing design patterns in the code.

    Args:
        question: The specific, high-level question you need an answer to.
                  (e.g., "What is the best design pattern for a modular plugin system in Python?")
        context: A string containing the relevant code, diff, or dossier summary to ground the question.
    """
    try:
        prompt = await build_prompt(
            scope="simula.architect_advisor",
            context={"question": question, "code_context": context},
            summary="Provide expert architectural advice based on the user's question and code context.",
        )
        response = await call_llm_service(prompt, agent_name="Simula.Architect")

        # Attempt to parse the response as JSON, but fall back to raw text if it fails.
        advice = extract_json_flex(response.text) or {"answer": response.text}

        return {"status": "success", "result": advice}
    except Exception as e:
        log.error(f"Architectural advice tool failed: {e!r}", exc_info=True)
        return {"status": "error", "reason": f"Failed to get architectural advice: {e!r}"}


async def _reflect_and_revise_plan(
    self,
    goal: str,
    executed_step: dict,
    outcome: dict,
    remaining_steps: list[dict],
) -> list[dict]:
    """
    After a tool executes, this method makes a quick LLM call to decide if the plan is still valid.
    """
    log.info("[SCL] 🤔 Reflecting on last action's outcome...")
    try:
        prompt = await build_prompt(
            scope="simula.plan_reflector",
            context={
                "goal": goal,
                "executed_step": executed_step,
                "outcome": outcome,
                "remaining_steps": remaining_steps,
            },
            summary="Given the last outcome, decide to continue or revise the plan.",
        )
        # Use a fast, cheap model for this decision
        llm_policy = {"model": "gpt-4o-mini", "temperature": 0.1}
        response = await call_llm_service(
            prompt,
            agent_name="Simula.Reflector",
            policy_override=llm_policy,
        )
        decision_obj = extract_json_flex(response.text)

        if decision_obj and decision_obj.get("decision") == "revise":
            new_plan = decision_obj.get("new_plan", [])
            if new_plan:
                log.info("[SCL] ♟️ Plan revised mid-flight based on new information.")
                return new_plan
    except Exception as e:
        log.warning(f"[SCL] Plan reflection step failed: {e!r}. Continuing with original plan.")

    return remaining_steps


@track_tool("plan_and_critique_strategy", modes=["simula_planful", "planning", "reasoning"])
async def plan_and_critique_strategy(
    *,
    goal: str,
    dossier: dict,
    turn_history: list,
) -> dict[str, Any]:
    """
    Performs a two-step strategic deliberation: first, propose a plan, then critique it to find flaws.

    This is a powerful meta-planning tool to prevent naive or flawed initial plans. It forces
    the agent to "think twice" by generating a strategy, then immediately using a separate
    "red team" persona to find weaknesses in that strategy, returning both for final consideration.
    Use this at the beginning of a complex task to ensure a robust approach.

    Args:
        goal: The high-level objective for the task.
        dossier: The context dossier for the code being worked on.
        turn_history: A history of previous turns in the current session to learn from.
    """
    try:
        # Step 1: Generate the initial plan
        plan_prompt = await build_prompt(
            scope="simula.strategic_planner",
            context={"goal": goal, "dossier": dossier, "turn_history": turn_history},
            summary="Generate a high-level strategic plan to accomplish the goal.",
        )
        plan_response = await call_llm_service(plan_prompt, agent_name="Simula.Strategist")
        initial_plan = extract_json_flex(plan_response.text)
        if not initial_plan:
            return {"status": "error", "reason": "Failed to generate an initial strategic plan."}

        # Step 2: Critique the plan
        critique_prompt = await build_prompt(
            scope="simula.strategy_critique",
            context={"goal": goal, "plan_to_critique": initial_plan},
            summary="Critique the proposed strategic plan for flaws, risks, and missed opportunities.",
        )
        critique_response = await call_llm_service(critique_prompt, agent_name="Simula.RedTeam")
        critique = extract_json_flex(critique_response.text)
        if not critique:
            return {"status": "error", "reason": "Failed to generate a critique of the plan."}

        return {
            "status": "success",
            "result": {
                "initial_plan": initial_plan,
                "critique": critique,
            },
        }
    except Exception as e:
        return {"status": "error", "reason": f"Strategic deliberation failed: {e!r}"}


@track_tool("create_pull_request", modes=["simula_planful", "vcs", "cortex"])
async def create_pull_request(
    repo_slug: str,
    title: str,
    head_branch: str,
    base_branch: str,
    body: str,
) -> dict[str, Any]:
    """
    [CORTEX TOOL] Creates a pull request on GitHub.
    Requires a GITHUB_TOKEN environment variable with repo access.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return {"status": "error", "reason": "GITHUB_TOKEN environment variable not set."}

    try:
        g = Github(token)
        repo = g.get_repo(repo_slug)
        pr = repo.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch,
        )
        log.info(f"Successfully created PR #{pr.number}: {pr.html_url}")
        return {"status": "success", "result": {"pr_number": pr.number, "url": pr.html_url}}
    except Exception as e:
        log.error(f"Failed to create pull request: {e!r}", exc_info=True)
        return {"status": "error", "reason": f"GitHub API call failed: {e!r}"}


@track_tool("record_recipe", modes=["simula_planful", "learning"])
async def record_recipe(
    *,
    goal: str,
    context_fqname: str,
    steps: list[str],
    success: bool,
    impact_hint: str = "",
) -> dict[str, Any]:
    """
    Saves a successful or failed sequence of actions as a 'recipe' for future learning.

    This tool is used for meta-learning. By recording the steps taken to solve a problem,
    the system can learn effective (or ineffective) patterns for similar tasks in the future.

    Args:
        goal: The original goal of the task.
        context_fqname: The fully-qualified name of the code context (e.g., file path).
        steps: A list of the actions/tool calls that were executed.
        success: Whether the final outcome was successful.
        impact_hint: A hint about the impact of the change.
    """
    r = append_recipe(
        goal=goal,
        context_fqname=context_fqname,
        steps=steps,
        success=success,
        impact_hint=impact_hint,
    )
    return {"status": "success", "recipe": r.__dict__}


# ==============================================================================
# SECTION: Qora & Nova Adapters (Reasoning & Learning)
# ==============================================================================


@track_tool("get_context_dossier", modes=["simula_planful", "reasoning", "general"])
async def get_context_dossier(*, target_fqname: str, intent: str) -> dict[str, Any]:
    """
    Fetches a comprehensive 'dossier' of context about a specific code element from Qora.

    This is the primary tool for gathering information before modifying existing code.
    The dossier includes source code, related tests, call graphs, documentation, and historical context.

    Args:
        target_fqname: The fully-qualified name of the target symbol (e.g., 'path/to/file.py::my_function').
        intent: The reason for fetching the dossier (e.g., 'implement', 'refactor', 'debug').
    """
    return await _api_call(
        "POST",
        "QORA_DOSSIER_BUILD",
        {"target_fqname": target_fqname, "intent": intent},
    )


@track_tool("qora_semantic_search", modes=["simula_planful", "reasoning"])
async def qora_semantic_search(*, query_text: str, top_k: int = 5) -> dict[str, Any]:
    """
    Performs a semantic search across the entire codebase for relevant code snippets.

    Use this tool to find examples, related logic, or alternative implementations
    when you are unsure where to start or need more context than a dossier provides.

    Args:
        query_text: The natural language search query.
        top_k: The maximum number of search results to return.
    """
    return await _api_call(
        "POST",
        "QORA_SEMANTIC_SEARCH",
        {"query_text": query_text, "top_k": top_k},
    )


@track_tool("reindex_code_graph", modes=["simula_planful", "administration"])
async def qora_reindex_code_graph(*, root: str = ".") -> dict[str, Any]:
    """
    Triggers a full re-indexing of the codebase to update the Qora knowledge graph.

    This is an administrative tool that should be used after significant changes to the
    codebase, such as merging a large feature branch, to ensure Qora's data is fresh.

    Args:
        root: The root directory of the codebase to index.
    """
    return await qora_client.reindex_code_graph(root=root)


# ==============================================================================
# SECTION: Filesystem & Code Operations (Sandboxed)
# ==============================================================================


@track_tool("read_file", modes=["simula_planful", "file_system", "reasoning", "general"])
async def read_file(*, path: str) -> dict[str, Any]:
    """
    Reads and returns the full content of a specified file from inside the sandbox.
    """
    cfg = seed_config()
    script = (
        "import sys, json; from pathlib import Path; "
        "p = Path(sys.argv[1]); "
        "if not p.exists() or not p.is_file(): "
        "  print(json.dumps({'ok': False, 'error': 'File not found.'})); sys.exit(0); "
        "data = p.read_text(encoding='utf-8', errors='replace'); "
        "print(json.dumps({'ok': True, 'content': data}))"
    )
    cmd = ["python", "-c", script, path]
    async with DockerSandbox(cfg).session() as sess:
        out = await sess._run_tool(cmd, timeout=60)

    if out.get("returncode", 1) != 0:
        return {"status": "error", "reason": f"File read failed: {out.get('stderr')}"}

    try:
        payload = json.loads(out.get("stdout") or "{}")
    except Exception as e:
        return {
            "status": "error",
            "reason": f"Malformed read output: {e} | raw={out.get('stdout')!r}",
        }

    if not payload.get("ok"):
        return {"status": "error", "reason": payload.get("error", "unknown error")}

    return {
        "status": "success",
        "result": {"path": path, "content": payload.get("content", "")},
    }


@track_tool("write_file", modes=["simula_planful", "file_system", "code_generation", "general"])
async def write_file(*, path: str, content: str, append: bool = False) -> dict[str, Any]:
    """
    Creates, overwrites, or appends to a file in the sandbox.
    """
    cfg = seed_config()
    mode = "a" if append else "w"
    script = (
        "import sys; from pathlib import Path; "
        "path, content, mode = sys.argv[1], sys.argv[2], sys.argv[3]; "
        "p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); "
        "with p.open(mode, encoding='utf-8', newline='\\n') as f: f.write(content)"
    )
    cmd = ["python", "-c", script, path, content, mode]
    async with DockerSandbox(cfg).session() as sess:
        out = await sess._run_tool(cmd, timeout=60)

    if out.get("returncode", 1) != 0:
        return {"status": "error", "reason": f"File write failed: {out.get('stderr')}"}

    return {"status": "success", "result": {"path": path}}


@track_tool("list_files", modes=["simula_planful", "file_system", "reasoning", "general"])
async def list_files(
    *,
    path: str = ".",
    recursive: bool = False,
    max_depth: int = 3,
) -> dict[str, Any]:
    """
    Lists files and directories to explore the project structure.

    Args:
        path: The directory to start listing from. Defaults to the project root.
        recursive: If True, lists files in all subdirectories.
        max_depth: The maximum depth for recursion.
    """
    cfg = seed_config()
    cmd = ["find", path, "-maxdepth", str(max_depth if recursive else 1)]
    async with DockerSandbox(cfg).session() as sess:
        out = await sess._run_tool(cmd, timeout=60)
    if out.get("returncode", 1) != 0:
        return {"status": "error", "reason": out.get("stderr") or "List files command failed."}
    items = [item for item in out.get("stdout", "").strip().splitlines() if item != path]
    return {"status": "success", "result": {"items": sorted(items[:2000])}}


@track_tool("file_search", modes=["simula_planful", "file_system", "reasoning"])
async def file_search(*, pattern: str, path: str = ".") -> dict[str, Any]:
    """
    Searches for a regex pattern within files in a directory. Returns matching file paths.

    Args:
        pattern: The regular expression to search for.
        path: The directory or file to search within. Defaults to the project root.
    """
    cfg = seed_config()
    cmd = ["grep", "-r", "-l", "-E", pattern, path]
    async with DockerSandbox(cfg).session() as sess:
        out = await sess._run_tool(cmd, timeout=120)
    if out.get("returncode", 1) > 1:
        return {"status": "error", "reason": out.get("stderr") or "Search command failed."}
    matches = out.get("stdout", "").strip().splitlines()
    return {"status": "success", "result": {"matches": matches}}


@track_tool("apply_refactor", modes=["simula_planful", "code_generation"])
async def apply_refactor(*, diff: str) -> dict[str, Any]:
    """
    Applies a git-formatted unified diff to the codebase in the sandbox.

    This is the standard way to apply code changes generated by an LLM or another tool.

    Args:
        diff: A string containing the unified diff to apply.
    """
    if not diff or not diff.strip():
        return {"status": "error", "reason": "diff cannot be empty"}

    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        applied = await sess.apply_unified_diff(diff)
        if not applied:
            return {"status": "error", "reason": "git apply failed"}
        return {"status": "success"}


# ==============================================================================
# SECTION: Quality, Testing & Hygiene (Sandboxed)
# ==============================================================================


@track_tool("generate_test_scenarios", modes=["simula_planful", "testing", "planning"])
async def generate_test_scenarios(*, goal: str, context: str) -> dict[str, Any]:
    """
    Analyzes a goal and code context to brainstorm potential test scenarios.

    This helps ensure thorough testing by thinking about edge cases, positive/negative
    paths, and potential vulnerabilities. It returns a list of human-readable scenarios.

    Args:
        goal: The original high-level goal for the code change.
        context: The relevant source code or diff to be tested.
    """
    try:
        prompt = await build_prompt(
            scope="simula.test_scenario_generator",
            context={"goal": goal, "context": context},
            summary="Generate a comprehensive list of test scenarios for the given code context.",
        )
        response = await call_llm_service(prompt, agent_name="Simula.TestStrategist")
        scenarios = extract_json_flex(response.text)
        return {"status": "success", "result": {"scenarios": scenarios or []}}
    except Exception as e:
        return {"status": "error", "reason": f"Failed to generate test scenarios: {e!r}"}


@track_tool("run_tests", modes=["simula_planful", "testing", "general"])
async def run_tests(*, paths: list[str] | None = None, timeout_sec: int = 900) -> dict[str, Any]:
    """
    Executes the test suite using pytest to verify code correctness.

    This is a critical step to ensure that code changes have not introduced any
    regressions and that new functionality works as expected. Always run this
    after writing or modifying code.

    Args:
        paths: Specific test files or directories to run. If None, runs all tests.
        timeout_sec: Maximum time in seconds to allow the test run to complete.
    """
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ok, logs = await sess.run_pytest(_normalize_paths(paths), timeout=timeout_sec)
        return {"status": "success" if ok else "failed", "result": {"passed": ok, "logs": logs}}


@track_tool("static_check", modes=["simula_planful", "code_analysis"])
async def static_check(*, paths: list[str] | None = None) -> dict[str, Any]:
    """
    Runs static analysis (ruff for linting, mypy for type checking) on the code.

    A crucial tool for catching bugs, style errors, and type inconsistencies before
    running any code. Should be used frequently during development.

    Args:
        paths: A list of files or directories to check.
    """
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ruff_out = await sess.run_ruff(_normalize_paths(paths))
        mypy_out = await sess.run_mypy(_normalize_paths(paths))
        ruff_ok = ruff_out.get("returncode", 1) == 0
        mypy_ok = mypy_out.get("returncode", 1) == 0
        return {
            "status": "success" if ruff_ok and mypy_ok else "failed",
            "result": {"ruff_ok": ruff_ok, "mypy_ok": mypy_ok, "ruff": ruff_out, "mypy": mypy_out},
        }


@track_tool("run_repair_engine", modes=["simula_planful", "code_generation", "debugging"])
async def run_repair_engine(
    *,
    paths: list[str] | None = None,
    timeout_sec: int = 600,
) -> dict[str, Any]:
    """
    Invokes the autonomous repair engine to attempt to fix failing tests.

    When tests fail, this tool can be used to automatically generate and apply a patch
    that resolves the issue. It uses LLMs and iterative testing to find a solution.

    Args:
        paths: The test files or source files associated with the failure.
        timeout_sec: The maximum time to spend on the repair attempt.
    """
    out = await attempt_repair(_normalize_paths(paths), timeout_sec=timeout_sec)
    return {
        "status": out.status,
        "result": {"diff": out.diff, "tried": out.tried, "notes": out.notes},
    }


@track_tool("run_tests_and_diagnose_failures", modes=["simula_planful", "testing", "debugging"])
async def run_tests_and_diagnose_failures(
    *,
    paths: list[str] | None = None,
    k_expr: str = "",
) -> dict[str, Any]:
    """
    Runs tests and, if they fail, parses the output to provide a structured diagnosis and suggests a root cause.

    This is more powerful than `run_tests` alone. It not only reports failure but also
    extracts the specific error messages and tracebacks, and then uses an LLM to hypothesize
    about the likely root cause of the failure, providing a strong starting point for debugging.

    Args:
        paths: The test files or directories to run.
        k_expr: An optional keyword expression to select a subset of tests.
    """
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        await ensure_toolchain(sess)
        ok, logs = await sess.run_pytest_select(_normalize_paths(paths), k_expr=k_expr, timeout=600)

    test_result = {"status": "success" if ok else "failed", "result": {"passed": ok, "logs": logs}}

    if ok:
        return test_result

    stdout = logs.get("stdout", "")
    try:
        failures = parse_pytest_output(stdout)
        diagnostics = {"parsed_failures": [f.__dict__ for f in failures]}

        if failures:
            diag_prompt = await build_prompt(
                scope="simula.failure_diagnoser",
                context={"test_failures": diagnostics},
                summary="Analyze test failures and suggest a probable root cause.",
            )
            diag_response = await call_llm_service(diag_prompt, agent_name="Simula.Diagnoser")
            diagnostics["root_cause_hypothesis"] = diag_response.text

        test_result["result"]["diagnostics"] = diagnostics
        return test_result
    except Exception as e:
        return {"status": "error", "reason": f"Test diagnostics failed: {e!r}", "logs": logs}


# ==============================================================================
# SECTION: VCS, CI/CD & Deployment
# ==============================================================================


@track_tool("open_pr", modes=["simula_planful", "vcs"])
async def open_pr(
    *,
    diff: str,
    title: str,
    evidence: dict | None = None,
    base: str = "main",
) -> dict:
    """
    Opens a new Pull Request (PR) in the version control system.

    This is typically one of the final steps in a development task, packaging the
    final code change for human review and merging.

    Args:
        diff: The git-formatted unified diff for the PR.
        title: The title of the Pull Request.
        evidence: A dictionary containing evidence of the change's validity (e.g., test results).
        base: The name of the base branch to open the PR against (e.g., 'main' or 'develop').
    """
    res = await _open_pr_impl(diff, title=title, evidence=evidence or {}, base=base)
    return res.__dict__


@track_tool("format_patch", modes=["simula_planful", "formatting"])
async def format_patch(*, paths: list[str]) -> dict:
    """
    Automatically formats code using the project's autoformatter (e.g., Black, ruff format).

    This should be run before committing code to ensure it conforms to the project's style guide.

    Args:
        paths: A list of files or directories to format.
    """
    return await autoformat_changed(_normalize_paths(paths))


@track_tool("conventional_commit_message", modes=["simula_planful", "vcs"])
async def conventional_commit_message(
    *,
    commit_type: str,
    scope: str | None,
    subject: str,
    body: str | None,
) -> dict[str, Any]:
    """
    Constructs a full Conventional Commits message from its component parts.

    This tool helps create well-formatted, detailed commit messages that follow a standard structure.

    Args:
        commit_type: The commit type (e.g., 'feat', 'fix', 'chore').
        scope: The part of the codebase affected (e.g., 'api', 'db').
        subject: The short, imperative-mood description of the change.
        body: A more detailed explanation of the change.
    """
    return {
        "status": "success",
        "message": render_conventional_commit(
            type_=commit_type,
            scope=scope,
            subject=subject,
            body=body,
        ),
    }


# ==============================================================================
# SECTION: Generic System & Memory Tools
# ==============================================================================


@track_tool("memory_write", modes=["simula_planful", "memory", "general"])
async def memory_write(*, key: str, value: Any) -> dict[str, Any]:
    """
    Writes a value to the agent's short-term key-value memory store (blackboard).

    Useful for saving state, intermediate results, or important context within a single
    multi-step task.

    Args:
        key: The key to store the value under.
        value: The value to store (can be any JSON-serializable type).
    """
    if not key or value is None:
        return {"status": "error", "reason": "key and value are required"}
    await _bb_write(key, value)
    return {"status": "success"}


@track_tool("memory_read", modes=["simula_planful", "memory", "general"])
async def memory_read(*, key: str) -> dict[str, Any]:
    """
    Reads a value from the agent's short-term key-value memory store (blackboard).

    Used to retrieve information that was previously saved with memory_write.

    Args:
        key: The key of the value to retrieve.
    """
    if not key:
        return {"status": "error", "reason": "key is required"}
    out = await _bb_read(key)
    return {"status": "success", "value": out}
