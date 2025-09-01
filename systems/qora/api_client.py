# systems/qora/api_client.py
# --- AMBITIOUS UPGRADE (ADDED GOAL CONTEXT CLIENT) ---
from __future__ import annotations

import os
import uuid
import logging
from typing import Any, Dict, Optional

from core.utils.net_api import ENDPOINTS, get_http_client

logger = logging.getLogger(__name__)

# ---- helpers ---------------------------------------------------------------

def _qora_key() -> str | None:
    return os.getenv("QORA_API_KEY") or os.getenv("EOS_API_KEY")

def _headers(
    decision_id: str | None = None,
    budget_ms: int | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if decision_id:
        headers["x-decision-id"] = decision_id
    if budget_ms is not None:
        headers["x-budget-ms"] = str(int(budget_ms))
    k = _qora_key()
    if k:
        headers["X-Qora-Key"] = k
    if extra:
        headers.update(extra)
    return headers

# --- Internal HTTP helpers --------------------------------------------------

async def _post(url: str, payload: dict, **kwargs) -> dict[str, Any]:
    client = await get_http_client()
    # allow callers to pass headers=..., but always include auth header
    hdrs = kwargs.pop("headers", {})
    headers = _headers(extra=hdrs)
    r = await client.post(url, json=payload, headers=headers, **kwargs)
    r.raise_for_status()
    data = r.json() or {}
    logger.debug("POST %s payload=%s -> %s", url, {k: payload.get(k) for k in list(payload)[:6]}, data)
    return data

async def _get(url: str, params: dict, **kwargs) -> dict[str, Any]:
    client = await get_http_client()
    hdrs = kwargs.pop("headers", {})
    headers = _headers(extra=hdrs)
    r = await client.get(url, params=params, headers=headers, **kwargs)
    r.raise_for_status()
    data = r.json() or {}
    logger.debug("GET %s params=%s -> %s", url, params, data)
    return data

# --- Qora Architecture (Tools) ---------------------------------------------

async def execute_by_query(query: str, args: dict, **kwargs) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_ARCH_EXECUTE_BY_QUERY")
    payload = {"query": query, "args": args, **kwargs}
    return await _post(url, payload)

# --- Qora World Model (Code Graph) -----------------------------------------

async def get_dossier(target_fqname: str, intent: str) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_DOSSIER_BUILD")
    payload = {"target_fqname": target_fqname, "intent": intent}
    return await _post(url, payload)

async def semantic_search(query_text: str, top_k: int = 5) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_CODE_GRAPH_SEMANTIC_SEARCH")
    return await _post(url, {"query_text": query_text, "top_k": top_k})

async def get_call_graph(target_fqn: str) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_CODE_GRAPH_CALL_GRAPH")
    return await _get(url, {"fqn": target_fqn})

async def get_goal_context(query_text: str, top_k: int = 3) -> dict[str, Any]:
    """NEW: Finds relevant code context based on a high-level goal."""
    url = getattr(ENDPOINTS, "QORA_CODE_GRAPH_GOAL_ORIENTED_CONTEXT")
    return await _post(url, {"query_text": query_text, "top_k": top_k})

async def reindex_code_graph(root: str = ".") -> dict[str, Any]:
    """Triggers a full re-ingestion of the Code Graph."""
    url = getattr(ENDPOINTS, "QORA_WM_REINDEX", "/qora/wm_admin/reindex")
    return await _post(url, {"root": root})

# --- Qora Governance & Learning Services -----------------------------------

async def get_constitution(agent: str, profile: str) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_CONSTITUTION_GET")
    return await _get(url, {"agent": agent, "profile": profile})

async def request_critique(diff: str) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_DELIBERATION_CRITIQUE")
    return await _post(url, {"diff": diff})

async def create_conflict(
    system: str,
    description: str,
    signature: str,
    context: dict,
) -> dict[str, Any]:
    """
    POST /qora/conflicts/create

    Body:
      {
        "system": "<agent/system name>",
        "description": "<what failed>",
        "signature": "<stable hash for this failure context>",
        "context": {...}  // optional
      }

    Returns API JSON (expected to include 'conflict_node').
    """
    url = getattr(ENDPOINTS, "QORA_CONFLICTS_CREATE")
    payload = {"system": system, "description": description, "signature": signature, "context": context}
    data = await _post(url, payload)
    return data

async def resolve_conflict(conflict_id: str, successful_diff: str) -> dict[str, Any]:
    """
    POST /qora/conflicts/{conflict_id}/resolve

    Body:
      { "successful_diff": "<unified diff>" }
    """
    url = ENDPOINTS.path("QORA_CONFLICTS_RESOLVE", conflict_id=conflict_id)
    payload = {"successful_diff": successful_diff}
    data = await _post(url, payload)
    return data

def extract_conflict_uuid(api_json: Dict[str, Any]) -> Optional[str]:
    """
    Normalize the UUID from the response of /qora/conflicts/create.

    Expected shape:
      {"ok": true, "conflict_node": {"uuid": "...", ...}}
    or:
      {"ok": true, "conflict_node": {"properties": {"uuid": "..."}, ...}}
    """
    node = (api_json or {}).get("conflict_node") or {}
    if not isinstance(node, dict):
        return None
    # Try direct field first
    uuid_val = node.get("uuid")
    if isinstance(uuid_val, str) and uuid_val:
        return uuid_val
    # Fallback to nested properties
    props = node.get("properties")
    if isinstance(props, dict):
        uuid_val = props.get("uuid")
        if isinstance(uuid_val, str) and uuid_val:
            return uuid_val
    # Last-ditch: common alternates
    for k in ("id", "ID", "pk"):
        v = node.get(k)
        if isinstance(v, str) and v:
            return v
    return None

async def find_similar_failures(goal: str, top_k: int = 3) -> dict[str, Any]:
    """Fully implemented function to learn from past failures."""
    url = getattr(ENDPOINTS, "QORA_LEARNING_FIND_FAILURES")
    return await _post(url, {"goal": goal, "top_k": top_k})

# --- Qora Blackboard (State) & Other Services ------------------------------

async def bb_write(key: str, value: Any, **kwargs) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_WM_BB_WRITE")
    return await _post(url, {"key": key, "value": value}, **kwargs)

async def bb_read(key: str, **kwargs) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_WM_BB_READ")
    return await _get(url, {"key": key}, **kwargs)

async def qora_impact_plan(diff: str, **kwargs) -> dict[str, Any]:
    url = getattr(ENDPOINTS, "QORA_IMPACT_PLAN")
    return await _post(url, {"diff_text": diff, **kwargs})
