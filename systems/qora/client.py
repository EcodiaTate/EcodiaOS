# systems/qora/client.py
# --- PROJECT SENTINEL UPGRADE (Corrected) ---
from __future__ import annotations

import logging
import os
from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client

# --- helpers ---------------------------------------------------------------


def _hdr() -> dict[str, str]:
    """Retrieves the Qora API key from environment variables."""
    key = os.getenv("QORA_API_KEY") or os.getenv("EOS_API_KEY")
    return {"X-Qora-Key": key} if key else {}


def _clean_params(d: dict[str, Any]) -> dict[str, Any]:
    """Removes None values from a dictionary to create a clean parameter set."""
    return {k: v for k, v in d.items() if v is not None}


# ---- catalog / tools -------------------------------------------------------


async def fetch_llm_tools(
    agent: str | None = None,
    capability: str | None = None,
    safety_max: int | None = None,
) -> list[dict[str, Any]]:
    """
    Returns a list of tool spec dicts. On any error, logs and raises an exception.
    """
    params: dict[str, Any] = _clean_params(
        {"agent": agent, "capability": capability, "safety_max": safety_max},
    )
    try:
        async with await get_http_client() as http:
            r = await http.get(ENDPOINTS.QORA_CATALOG, params=params, timeout=15.0)
            r.raise_for_status()
            data = r.json() or {}
        tools = data.get("tools", [])
        return [dict(t) for t in tools]
    except Exception as e:
        logging.exception("Failed to fetch LLM tools from Qora catalog.")
        raise OSError("Could not connect to or parse Qora tool catalog.") from e


# ---- arch (semantic) search + execution -----------------------------------


async def qora_search(
    query: str,
    top_k: int = 5,
    safety_max: int | None = 2,
    system: str | None = None,
) -> dict[str, Any]:
    """POST /arch/search. Returns the full, structured response."""
    payload = _clean_params(
        {"query": query, "top_k": top_k, "safety_max": safety_max, "system": system},
    )
    async with await get_http_client() as http:
        r = await http.post(ENDPOINTS.QORA_SEARCH, json=payload, headers=_hdr(), timeout=60.0)
        r.raise_for_status()
        return r.json() or {}


async def qora_schema(uid: str) -> dict[str, Any]:
    """
    GET /arch/schema/{uid}. This function is restored to fix the ImportError.
    """
    async with await get_http_client() as http:
        # Robustly handle templated URLs from the ENDPOINTS overlay
        url = ENDPOINTS.path("QORA_ARCH_SCHEMA_UID", uid=uid)
        r = await http.get(url, headers=_hdr(), timeout=30.0)
        r.raise_for_status()
        return r.json() or {}


async def qora_exec_by_uid(
    uid: str,
    args: dict[str, Any],
    *,
    caller: str | None = None,
    log: bool = True,
) -> dict[str, Any]:
    """POST /arch/execute-by-uid"""
    payload = {"uid": uid, "args": args, "caller": caller, "log": log}
    async with await get_http_client() as http:
        r = await http.post(
            ENDPOINTS.QORA_EXECUTE_BY_UID,
            json=payload,
            headers=_hdr(),
            timeout=300.0,
        )
        r.raise_for_status()
        return r.json() or {}


async def qora_exec_by_query(
    query: str,
    args: dict[str, Any],
    *,
    caller: str | None = None,
    top_k: int = 3,
    safety_max: int | None = 2,
    system: str | None = None,
    log: bool = True,
) -> dict[str, Any]:
    """POST /arch/execute-by-query"""
    payload = _clean_params(
        {
            "query": query,
            "args": args,
            "caller": caller,
            "top_k": top_k,
            "safety_max": safety_max,
            "system": system,
            "log": log,
        },
    )
    async with await get_http_client() as http:
        r = await http.post(
            ENDPOINTS.QORA_EXECUTE_BY_QUERY,
            json=payload,
            headers=_hdr(),
            timeout=300.0,
        )
        r.raise_for_status()
        return r.json() or {}
