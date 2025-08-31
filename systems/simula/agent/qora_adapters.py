# systems/simula/agent/qora_adapters.py
# --- FULL FIXED FILE ---
from __future__ import annotations

from systems.qora.api_client import get_dossier, semantic_search, get_call_graph, get_goal_context
from core.utils.eos_tool import eos_tool
from typing import Any
from systems.qora import api_client as qora_client

from core.utils.net_api import ENDPOINTS, get_http_client

# --- Unified HTTP Helper ---


async def _api_call(
    method: str,
    endpoint_name: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """
    A single, robust helper for making API calls to Qora services.
    It handles endpoint resolution, status checking, and wraps all responses
    in a standardized {'status': '...', 'result': ...} schema.
    """
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
        return {
            "status": "error",
            "reason": f"Configuration error: Endpoint '{endpoint_name}' not found in live service registry.",
        }
    except Exception as e:
        return {"status": "error", "reason": f"API call to '{endpoint_name}' failed: {e!r}"}


@eos_tool(
    name="qora.get_dossier",
    description="Builds a comprehensive dossier for a given code entity (file, class, or function) based on an intent.",
    inputs={
        "type": "object",
        "properties": {
            "target_fqname": {"type": "string", "description": "The fully qualified name of the target symbol, e.g., 'systems/simula/agent/orchestrator.py::AgentOrchestrator'."},
            "intent": {"type": "string", "description": "The user's high-level goal, e.g., 'add a new feature'."}
        },
        "required": ["target_fqname", "intent"]
    },
    outputs={"type": "object"}
)
async def qora_get_dossier(target_fqname: str, intent: str) -> dict[str, Any]:
    """Adapter for the Qora get_dossier endpoint."""
    return await get_dossier(target_fqname, intent)

@eos_tool(
    name="qora.semantic_search",
    description="Performs semantic search over the entire codebase knowledge graph.",
    inputs={
        "type": "object",
        "properties": {
            "query_text": {"type": "string", "description": "The natural language query to search for."},
            "top_k": {"type": "integer", "default": 5}
        },
        "required": ["query_text"]
    },
    outputs={"type": "object"}
)
async def qora_semantic_search(query_text: str, top_k: int = 5) -> dict[str, Any]:
    """Adapter for the Qora semantic_search endpoint."""
    return await semantic_search(query_text, top_k)

@eos_tool(
    name="qora.get_call_graph",
    description="Retrieves the direct call graph (callers and callees) for a specific function.",
    inputs={
        "type": "object",
        "properties": {
            "target_fqn": {"type": "string", "description": "The fully qualified name of the target function."}
        },
        "required": ["target_fqn"]
    },
    outputs={"type": "object"}
)
async def qora_get_call_graph(target_fqn: str) -> dict[str, Any]:
    """Adapter for the Qora get_call_graph endpoint."""
    return await get_call_graph(target_fqn)

@eos_tool(
    name="qora.get_goal_context",
    description="Finds relevant code snippets and symbols across the codebase related to a high-level goal.",
    inputs={
        "type": "object",
        "properties": {
            "query_text": {"type": "string", "description": "The high-level goal, e.g., 'implement user authentication'."},
            "top_k": {"type": "integer", "default": 3}
        },
        "required": ["query_text"]
    },
    outputs={"type": "object"}
)
async def qora_get_goal_context(query_text: str, top_k: int = 3) -> dict[str, Any]:
    """
    Adapter for the Qora get_goal_context endpoint.
    
    """
    return await get_goal_context(query_text, top_k)

async def qora_wm_search(*, q: str, top_k: int = 25) -> dict[str, Any]:
    return await _api_call("POST", "QORA_WM_SEARCH", {"q": q, "top_k": top_k})


async def qora_impact_plan(*, diff: str, include_coverage: bool = True) -> dict[str, Any]:
    return await _api_call(
        "POST",
        "QORA_IMPACT_PLAN",
        {"diff_text": diff, "include_coverage": include_coverage},
    )


async def qora_policy_check_diff(*, diff: str) -> dict[str, Any]:
    return await _api_call("POST", "QORA_POLICY_CHECK_DIFF", {"diff_text": diff})


async def qora_shadow_run(
    *,
    diff: str,
    min_delta_cov: float = 0.0,
    timeout_sec: int = 1200,
    run_safety: bool = True,
    use_xdist: bool = True,
) -> dict[str, Any]:
    payload = {
        "diff": diff,
        "min_delta_cov": min_delta_cov,
        "timeout_sec": timeout_sec,
        "run_safety": run_safety,
        "use_xdist": use_xdist,
    }
    return await _api_call("POST", "QORA_SHADOW_RUN", payload)


async def qora_bb_write(*, key: str, value: Any) -> dict[str, Any]:
    return await _api_call("POST", "QORA_BB_WRITE", {"key": key, "value": value})


async def qora_bb_read(*, key: str) -> dict[str, Any]:
    return await _api_call("GET", "QORA_BB_READ", {"key": key})


async def qora_proposal_bundle(
    *,
    proposal: dict,
    include_snapshot: bool = True,
    min_delta_cov: float = 0.0,
    add_safety_summary: bool = True,
) -> dict[str, Any]:
    payload = {
        "proposal": proposal,
        "include_snapshot": include_snapshot,
        "min_delta_cov": min_delta_cov,
        "add_safety_summary": add_safety_summary,
    }
    return await _api_call("POST", "QORA_PROPOSAL_BUNDLE", payload)


async def qora_hygiene_check(*, diff: str, auto_heal: bool, timeout_sec: int) -> dict[str, Any]:
    payload = {"diff": diff, "auto_heal": auto_heal, "timeout_sec": timeout_sec}
    return await _api_call("POST", "QORA_HYGIENE_CHECK", payload, timeout=timeout_sec + 30)


# NEW: Adapter for the powerful graph ingestor
async def qora_reindex_code_graph(*, root: str = ".") -> dict[str, Any]:
    """Adapter for the new graph re-indexing client function."""
    return await qora_client.reindex_code_graph(root=root)


# --- Adapters for NEW Ambitious Tools ---

async def request_critique(params: dict) -> dict[str, Any]:
    """Adapter for the multi-agent deliberation service."""
    return await qora_client.request_critique(**params)

async def find_similar_failures(params: dict) -> dict[str, Any]:
    """Adapter for the learning-from-failure service."""
    return await qora_client.find_similar_failures(**params)

async def qora_secrets_scan(
    *,
    paths: list[str] | None = None,
    use_heavy: bool = True,
    limit: int = 5000,
) -> dict[str, Any]:
    return await _api_call(
        "POST",
        "QORA_SECRETS_SCAN",
        {"paths": paths, "use_heavy": use_heavy, "limit": limit},
    )


async def qora_spec_eval_run(
    *,
    candidates: list[dict],
    min_delta_cov: float = 0.0,
    timeout_sec: int = 900,
    max_parallel: int = 4,
    score_weights: dict | None = None,
    emit_markdown: bool = True,
) -> dict[str, Any]:
    payload = {
        "candidates": candidates,
        "min_delta_cov": min_delta_cov,
        "timeout_sec": timeout_sec,
        "max_parallel": max_parallel,
        "score_weights": score_weights,
        "emit_markdown": emit_markdown,
    }
    return await _api_call("POST", "QORA_SPEC_EVAL_RUN", payload, timeout=timeout_sec + 30)