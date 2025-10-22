# --- AMBITIOUS UPGRADE (ADDED GOAL CONTEXT CLIENT) ---
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, Optional

from httpx import HTTPStatusError

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


async def _api_call(
    method: str,
    endpoint_name: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
    **kwargs,
) -> dict[str, Any]:
    """
    A single, robust helper for making API calls. It handles endpoint resolution,
    status checking, and wraps all responses in a standardized dictionary format,
    preventing crashes from HTTP errors.
    """
    try:
        http = await get_http_client()
        url = getattr(ENDPOINTS, endpoint_name)

        # Allow callers to pass headers=..., but always include auth headers
        hdrs = kwargs.pop("headers", {})
        headers = _headers(extra=hdrs)

        if method.upper() == "POST":
            response = await http.post(
                url,
                json=payload or {},
                headers=headers,
                timeout=timeout,
                **kwargs,
            )
        elif method.upper() == "GET":
            response = await http.get(
                url,
                params=payload or {},
                headers=headers,
                timeout=timeout,
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status()
        data = response.json() or {}
        logger.debug("%s %s -> %s", method.upper(), url, data)
        # Ensure a consistent success wrapper if the service doesn't provide one
        if "status" not in data:
            return {"status": "success", "result": data}
        return data

    except AttributeError:
        msg = f"Configuration error: Endpoint '{endpoint_name}' not found."
        logger.error(msg)
        return {"status": "error", "reason": msg}
    except HTTPStatusError as e:
        msg = f"API call to '{endpoint_name}' failed with status {e.response.status_code}: {e.response.text}"
        logger.warning(msg)
        return {"status": "error", "reason": msg}
    except Exception as e:
        msg = f"API call to '{endpoint_name}' failed: {e!r}"
        logger.error(msg, exc_info=True)
        return {"status": "error", "reason": msg}


# --- Qora Architecture (Tools) ---------------------------------------------


async def execute_by_query(query: str, args: dict, **kwargs) -> dict[str, Any]:
    payload = {"query": query, "args": args, **kwargs}
    return await _api_call("POST", "QORA_ARCH_EXECUTE_BY_QUERY", payload)


# --- Qora World Model (Code Graph) -----------------------------------------


async def get_dossier(target_fqname: str, intent: str) -> dict[str, Any]:
    payload = {"target_fqname": target_fqname, "intent": intent}
    # The original call was failing here. It now uses the robust helper.
    return await _api_call("POST", "QORA_DOSSIER_BUILD", payload)


async def semantic_search(query_text: str, top_k: int = 5) -> dict[str, Any]:
    payload = {"query_text": query_text, "top_k": top_k}
    return await _api_call("POST", "QORA_CODE_GRAPH_SEMANTIC_SEARCH", payload)


async def get_call_graph(target_fqn: str) -> dict[str, Any]:
    return await _api_call("GET", "QORA_CODE_GRAPH_CALL_GRAPH", {"fqn": target_fqn})


async def get_goal_context(query_text: str, top_k: int = 3) -> dict[str, Any]:
    """NEW: Finds relevant code context based on a high-level goal."""
    payload = {"query_text": query_text, "top_k": top_k}
    return await _api_call("POST", "QORA_CODE_GRAPH_GOAL_ORIENTED_CONTEXT", payload)


async def reindex_code_graph(root: str = ".") -> dict[str, Any]:
    """Triggers a full re-ingestion of the Code Graph."""
    return await _api_call("POST", "QORA_WM_REINDEX", {"root": root})


# --- Qora Governance & Learning Services -----------------------------------


async def get_constitution(agent: str, profile: str) -> dict[str, Any]:
    return await _api_call("GET", "QORA_CONSTITUTION_GET", {"agent": agent, "profile": profile})


async def request_critique(diff: str) -> dict[str, Any]:
    return await _api_call("POST", "QORA_DELIBERATION_CRITIQUE", {"diff": diff})


async def create_conflict(
    system: str,
    description: str,
    signature: str,
    context: dict,
) -> dict[str, Any]:
    payload = {
        "system": system,
        "description": description,
        "signature": signature,
        "context": context,
    }
    return await _api_call("POST", "QORA_CONFLICTS_CREATE", payload)


async def resolve_conflict(conflict_id: str, successful_diff: str) -> dict[str, Any]:
    url_path = ENDPOINTS.path("QORA_CONFLICTS_RESOLVE", conflict_id=conflict_id)
    # This is a special case; we can't use _api_call directly if the URL is dynamically formatted.
    # We will reconstruct a minimal version of the original _post for this one case.
    client = await get_http_client()
    headers = _headers()
    r = await client.post(url_path, json={"successful_diff": successful_diff}, headers=headers)
    r.raise_for_status()
    return r.json() or {}


def extract_conflict_uuid(api_json: dict[str, Any]) -> str | None:
    node = (api_json or {}).get("conflict_node") or {}
    if not isinstance(node, dict):
        return None
    uuid_val = node.get("uuid")
    if isinstance(uuid_val, str) and uuid_val:
        return uuid_val
    props = node.get("properties")
    if isinstance(props, dict):
        uuid_val = props.get("uuid")
        if isinstance(uuid_val, str) and uuid_val:
            return uuid_val
    for k in ("id", "ID", "pk"):
        v = node.get(k)
        if isinstance(v, str) and v:
            return v
    return None


async def find_similar_failures(goal: str, top_k: int = 3) -> dict[str, Any]:
    """Fully implemented function to learn from past failures."""
    return await _api_call("POST", "QORA_LEARNING_FIND_FAILURES", {"goal": goal, "top_k": top_k})


# --- Qora Blackboard (State) & Other Services ------------------------------


async def bb_write(key: str, value: Any, **kwargs) -> dict[str, Any]:
    return await _api_call("POST", "QORA_WM_BB_WRITE", {"key": key, "value": value}, **kwargs)


async def bb_read(key: str, **kwargs) -> dict[str, Any]:
    return await _api_call("GET", "QORA_WM_BB_READ", {"key": key}, **kwargs)


async def qora_impact_plan(diff: str, **kwargs) -> dict[str, Any]:
    payload = {"diff_text": diff, **kwargs}
    return await _api_call("POST", "QORA_IMPACT_PLAN", payload)
