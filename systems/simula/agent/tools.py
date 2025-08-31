# systems/simula/agent/tools.py
from __future__ import annotations

import ast
import io
import textwrap
from pathlib import Path
from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.qora.client import (
    qora_exec_by_query as _qora_exec_by_query,
)
from systems.qora.client import (
    qora_exec_by_uid as _qora_exec_by_uid,
)
from systems.qora.client import (
    qora_schema as _qora_schema,
)

# Qora ARCH (catalog/exec) — keep existing client for backward compatibility
from systems.qora.client import (
    qora_search as _qora_search,
)
from systems.simula.code_sim.fuzz.hypo_driver import run_hypothesis_smoke
from systems.simula.code_sim.repair.engine import attempt_repair
from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config

# Sandbox utilities (quality)
try:
    from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
    from systems.simula.code_sim.sandbox.seeds import seed_config
except Exception:  # soft import for environments without sandbox
    DockerSandbox = None  # type: ignore
    seed_config = lambda: {}  # type: ignore

# ---------------- Qora HTTP Adapters (no local clients) ---------------------
# Uses ENDPOINTS (if present) with sane fallbacks to the literal paths from your OpenAPI.


async def _post(path: str, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    http = await get_http_client()
    r = await http.post(path, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}  # type: ignore[return-value]


async def _get(path: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    http = await get_http_client()
    r = await http.get(path, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}  # type: ignore[return-value]


# --- Qora ARCH (search/schema/execute) ---
async def _qora_search(query: str, top_k: int = 5) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_ARCH_SEARCH", "/qora/arch/search")
    return await _post(url, {"query": query, "top_k": int(top_k)})


async def _qora_schema(uid: str) -> dict[str, Any]:
    # GET /qora/arch/schema/{uid}
    base = getattr(ENDPOINTS, "QORA_ARCH_SCHEMA", "/qora/arch/schema")
    url = f"{base}/{uid}"
    return await _get(url, {})


async def _qora_exec_by_uid(uid: str, args: dict[str, Any]) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_ARCH_EXEC_UID", "/qora/arch/execute-by-uid")
    return await _post(url, {"uid": uid, "args": args})


async def _qora_exec_by_query(
    query: str,
    args: dict[str, Any],
    *,
    top_k: int = 1,
    safety_max: int = 3,
    system: str = "*",
) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_ARCH_EXEC_QUERY", "/qora/arch/execute-by-query")
    return await _post(
        url,
        {
            "query": query,
            "args": args,
            "top_k": int(top_k),
            "safety_max": int(safety_max),
            "system": system,
        },
    )


# --- Qora Dossier (builder) ---
async def _get_dossier(target_fqname: str, *, intent: str) -> dict[str, Any]:
    # POST /qora/dossier/build
    url = getattr(ENDPOINTS, "QORA_DOSSIER_BUILD", "/qora/dossier/build")
    return await _post(url, {"target_fqname": target_fqname, "intent": intent})


# --- Qora Blackboard KV ---
async def _bb_write(key: str, value: Any) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_BB_WRITE", "/qora/bb/write")
    return await _post(url, {"key": key, "value": value})


async def _bb_read(key: str) -> Any:
    url = getattr(ENDPOINTS, "QORA_BB_READ", "/qora/bb/read")
    out = await _get(url, {"key": key})
    return out.get("value") if isinstance(out, dict) else out


# ---------------- Qora ARCH (execute system tools) --------------------------


async def execute_system_tool(params: dict[str, Any]) -> dict[str, Any]:
    uid = params.get("uid")
    query = params.get("query")
    args = params.get("args") or {}
    top_k = int(params.get("top_k") or 1)
    safety_max = int(params.get("safety_max") or 3)
    system = params.get("system") or "*"

    if not uid and not query:
        return {"status": "error", "reason": "Provide either uid or query"}

    if uid:
        return await _qora_exec_by_uid(uid, args)
    return await _qora_exec_by_query(query, args, top_k=top_k, safety_max=safety_max, system=system)


async def execute_system_tool_strict(params: dict[str, Any]) -> dict[str, Any]:
    """Validate inputs against live Qora schema before executing."""
    uid = params.get("uid")
    query = params.get("query")
    args = params.get("args") or {}

    if not uid and not query:
        return {"status": "error", "reason": "Provide either uid or query"}

    # Resolve uid via search when only a query is provided
    if not uid and query:
        found = await _qora_search(query, top_k=1)
        items = (found or {}).get("candidates") or []
        if not items:
            return {"status": "error", "reason": "No matching tool found"}
        uid = items[0].get("uid")

    sch = await _qora_schema(uid)
    input_schema = (sch or {}).get("inputs") or {}

    # Minimal schema enforcement: ensure required keys exist
    required = list(input_schema.get("required") or [])
    missing = [k for k in required if k not in args]
    if missing:
        return {"status": "error", "reason": f"Missing required args: {missing}"}

    return await _qora_exec_by_uid(uid, args)


# ---------------- World Model & Memory (Qora WM) ----------------------------


async def get_context_dossier(params: dict[str, Any]) -> dict[str, Any]:
    target = params.get("target_fqname")
    intent = params.get("intent")
    if not target or not intent:
        return {"status": "error", "reason": "target_fqname and intent are required"}
    return await _get_dossier(target, intent=intent)


async def memory_write(params: dict[str, Any]) -> dict[str, Any]:
    k, v = params.get("key"), params.get("value")
    if not k:
        return {"status": "error", "reason": "key required"}
    if v is None:
        return {"status": "error", "reason": "value required"}
    await _bb_write(k, v)
    return {"status": "success"}


async def memory_read(params: dict[str, Any]) -> dict[str, Any]:
    k = params.get("key")
    if not k:
        return {"status": "error", "reason": "key required"}
    out = await _bb_read(k)
    return {"status": "success", "value": out.get("value") if isinstance(out, dict) else out}


# ---------------- Quality: generate tests / static / pytest -----------------

_PREAMBLE = """# This file was generated by Simula.\n# Intent: add safety/contract coverage for the module under test.\n"""


def _discover_functions(src: str) -> list[str]:
    names: list[str] = []
    try:
        tree = ast.parse(src)
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
                names.append(n.name)
    except Exception:
        pass
    return names


async def generate_tests(params: dict[str, Any]) -> dict[str, Any]:
    module = params.get("module")
    if not module:
        return {"status": "error", "reason": "module required"}

    path = Path(module)
    if not path.exists():
        return {"status": "error", "reason": f"Module not found: {module}"}

    src = path.read_text(encoding="utf-8")
    fn_names = _discover_functions(src)

    tests_dir = Path("tests")
    tests_dir.mkdir(exist_ok=True)
    test_path = tests_dir / f"test_{path.stem}.py"

    body = io.StringIO()
    body.write(_PREAMBLE)
    body.write("import pytest\n")
    try:
        rel = path.as_posix()
        import_line = f"from {rel[:-3].replace('/', '.')} import *" if rel.endswith(".py") else ""
        if import_line:
            body.write(import_line + "\n\n")
    except Exception:
        pass

    if not fn_names:
        body.write(
            textwrap.dedent(
                f"""
            def test_module_imports():
                assert True, "module imports successfully"
            """,
            ),
        )
    else:
        for name in fn_names[:15]:  # cap to avoid explosion
            body.write(
                textwrap.dedent(
                    f"""
                def test_{name}_smoke():
                    # TODO: replace with meaningful inputs/expected outputs
                    try:
                        _ = {name}  # reference exists
                    except Exception as e:
                        pytest.fail(f"symbol {name} missing: {{!r}}".format(e))
                """,
                ),
            )

    content = body.getvalue()
    # Return as a proposed file edit; orchestrator may apply via apply_refactor
    return {"status": "proposed", "files": [{"path": str(test_path), "content": content}]}


async def static_check(params: dict[str, Any]) -> dict[str, Any]:
    paths = list(params.get("paths") or [])
    if not paths:
        return {"status": "error", "reason": "paths required"}
    if DockerSandbox is None:
        return {"status": "error", "reason": "Sandbox unavailable"}
    async with DockerSandbox(seed_config()).session():  # type: ignore
        # run tools directly on host workspace mounted in sandbox
        mypy = await DockerSandbox(seed_config()).run_mypy(paths)  # type: ignore
        ruff = await DockerSandbox(seed_config()).run_ruff(paths)  # type: ignore
        return {"status": "success", "mypy": mypy, "ruff": ruff}


async def run_tests(params: dict[str, Any]) -> dict[str, Any]:
    paths = list(params.get("paths") or [])
    timeout = int(params.get("timeout_sec") or 900)
    if not paths:
        return {"status": "error", "reason": "paths required"}
    if DockerSandbox is None:
        return {"status": "error", "reason": "Sandbox unavailable"}
    async with DockerSandbox(seed_config()).session():  # type: ignore
        ok, logs = await DockerSandbox(seed_config()).run_pytest(paths, timeout=timeout)  # type: ignore
        return {"status": "success" if ok else "failed", "logs": logs}


async def run_tests_k(params: dict[str, Any]) -> dict[str, Any]:
    paths: list[str] = params.get("paths") or ["tests"]
    k_expr: str = params.get("k_expr") or ""
    timeout_sec: int = int(params.get("timeout_sec") or 600)
    async with DockerSandbox(seed_config()).session() as sess:
        ok, logs = await sess.run_pytest_select(paths, k_expr, timeout=timeout_sec)
        return {"status": "success" if ok else "failed", "k": k_expr, "logs": logs}


async def apply_refactor(params: dict[str, Any]) -> dict[str, Any]:
    diff = params.get("diff")
    verify_paths = list(params.get("verify_paths") or [])
    if not diff:
        return {"status": "error", "reason": "diff required"}
    if DockerSandbox is None:
        return {"status": "error", "reason": "Sandbox unavailable"}
    async with DockerSandbox(seed_config()).session():  # type: ignore
        applied = await DockerSandbox(seed_config()).apply_unified_diff(diff)  # type: ignore
        if not applied:
            return {"status": "error", "reason": "apply failed"}
        if verify_paths:
            ok, logs = await DockerSandbox(seed_config()).run_pytest(verify_paths, timeout=900)  # type: ignore
            return {"status": "success" if ok else "failed", "logs": logs}
        return {"status": "success"}


# systems/simula/agent/tools.py  (append safe repair tool exposing engine)


async def run_repair_engine(params: dict[str, Any]) -> dict[str, Any]:
    paths: list[str] = params.get("paths") or []
    timeout_sec = int(params.get("timeout_sec") or 600)
    out = await attempt_repair(paths, timeout_sec=timeout_sec)
    return {"status": out.status, "diff": out.diff, "tried": out.tried, "notes": out.notes}


# systems/simula/agent/tools.py  (append safe wrappers)


async def run_tests_xdist(params: dict[str, Any]) -> dict[str, Any]:
    paths: list[str] = params.get("paths") or ["tests"]
    nprocs = params.get("nprocs") or "auto"
    timeout_sec = int(params.get("timeout_sec") or 900)
    async with DockerSandbox(seed_config()).session() as sess:
        ok, logs = await sess.run_pytest_xdist(paths, nprocs=nprocs, timeout=timeout_sec)
        return {"status": "success" if ok else "failed", "nprocs": nprocs, "logs": logs}


async def run_fuzz_smoke(params: dict[str, Any]) -> dict[str, Any]:
    """
    Best-effort hypothesis smoke test for a function symbol.
    Pass module path and function name explicitly to avoid import ambiguity.
    """
    mod_path = params.get("module")
    func_name = params.get("function")
    timeout_sec = int(params.get("timeout_sec") or 600)
    if not mod_path or not func_name:
        return {"status": "error", "reason": "module and function are required"}
    ok, logs = await run_hypothesis_smoke(mod_path, func_name, timeout_sec=timeout_sec)
    return {"status": "success" if ok else "failed", "logs": logs}


# ---------------- Hierarchical skills (thin HTTP wrappers) ------------------


async def continue_hierarchical_skill(params: dict[str, Any]) -> dict[str, Any]:
    episode_id = params.get("episode_id")
    step = params.get("step") or {}
    if not episode_id:
        return {"status": "error", "reason": "episode_id required"}
    try:
        http = await get_http_client()
        resp = await http.post(
            ENDPOINTS.SYNAPSE_CONTINUE_SKILL,
            json={"episode_id": episode_id, "step": step},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"status": "error", "reason": f"continue_skill HTTP failed: {e!r}"}


async def request_skill_repair(params: dict[str, Any]) -> dict[str, Any]:
    episode_id = params.get("episode_id")
    failed_step_index = params.get("failed_step_index")
    error_observation = params.get("error_observation")
    if not episode_id or failed_step_index is None or error_observation is None:
        return {
            "status": "error",
            "reason": "episode_id, failed_step_index, error_observation required",
        }
    try:
        http = await get_http_client()
        resp = await http.post(
            ENDPOINTS.SYNAPSE_REPAIR_SKILL_STEP,
            json={
                "episode_id": episode_id,
                "failed_step_index": int(failed_step_index),
                "error_observation": error_observation,
            },
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"status": "error", "reason": f"repair_skill_step HTTP failed: {e!r}"}
