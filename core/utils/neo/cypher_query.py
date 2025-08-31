# core/utils/neo/cypher_query.py
#
# Minimal, driverless Cypher helper (async).
# - No business-layer imports.
# - Resolves the Neo4j AsyncDriver internally via core.utils.neo.neo_driver.get_driver().
# - Safe to use across the codebase: infra-only, no circular deps.
#
from __future__ import annotations

import os
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Any, List, Dict, Optional

from neo4j import AsyncDriver  # type: ignore

from core.utils.neo.neo_driver import get_driver  # singleton AsyncDriver provider

NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


# ============================================================================
# Parameter coercion (Neo-safe)
# - DO NOT auto-parse JSON-looking strings.
# - For *property maps* (keys 'props' or '*_props'): convert leaf dicts / lists
#   containing non-primitives into JSON strings (Neo props must be primitives
#   or arrays of primitives).
# - Elsewhere, keep maps as maps so Cypher can use them structurally.
# ============================================================================

_PRIMS = (str, int, float, bool, type(None))

def _primify_base(v: Any) -> Any:
    """Normalize common non-primitive leaf types to primitives first."""
    # pydantic v2 / v1
    if hasattr(v, "model_dump"):
        try:
            v = v.model_dump()
        except Exception:
            pass
    elif hasattr(v, "dict"):
        try:
            v = v.dict()
        except Exception:
            pass

    # enums / datetimes → strings
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, (datetime, date)):
        return v.isoformat()

    # numpy → list
    try:
        import numpy as np  # type: ignore
        if isinstance(v, np.ndarray):
            return v.tolist()
    except Exception:
        pass

    return v


def _as_primitive_or_json(v: Any) -> Any:
    """
    Leaf rule for property values:
    - primitive: keep
    - list/tuple of primitives: keep as list
    - list/tuple with any non-primitive: JSON string
    - dict/other complex: JSON string
    """
    v = _primify_base(v)
    if isinstance(v, _PRIMS):
        return v
    if isinstance(v, (list, tuple)):
        if any(not isinstance(x, _PRIMS) for x in v):
            return json.dumps(v, ensure_ascii=False)
        return list(v)
    if isinstance(v, Mapping):
        return json.dumps(v, ensure_ascii=False)
    return json.dumps(v, ensure_ascii=False)


def _safe_property_map(d: Mapping[str, Any]) -> Dict[str, Any]:
    """Make a property map safe for `SET n += $props`."""
    return {str(k): _as_primitive_or_json(v) for k, v in d.items()}


def _coerce_general(v: Any) -> Any:
    """
    General param coercion (non-property-map): keep maps as maps so Cypher can
    access fields structurally. DO NOT json.loads any strings here.
    """
    v = _primify_base(v)
    if isinstance(v, (list, tuple)):
        return [_coerce_general(x) for x in v]
    if isinstance(v, Mapping):
        return {str(k): _coerce_general(x) for k, x in v.items()}
    return v


def neo_safe_params(params: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not params:
        return {}
    out: Dict[str, Any] = {}
    for k, v in params.items():
        key = str(k)
        if isinstance(v, Mapping) and (key == "props" or key.endswith("_props")):
            out[key] = _safe_property_map(v)
        else:
            out[key] = _coerce_general(v)
    return out


# ============================================================================
# Query helpers
# ============================================================================

async def cypher_query(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    driver: Optional[AsyncDriver] = None,
    database: Optional[str] = None,
    as_dict: bool = True,
    timeout_s: Optional[float] = None,
    bookmarks: Optional[Sequence[str] | str] = None,
) -> List[Any]:
    """
    Execute a Cypher query and return all records.

    Args:
        query: Cypher query string.
        params: Query parameters (dict).
        driver: Optional AsyncDriver override; if not provided, uses get_driver().
        database: Neo4j database name (defaults to env NEO4J_DATABASE or 'neo4j').
        as_dict: If True, return each record as dict; else return neo4j.Record objects.
        timeout_s: Optional per-query timeout in seconds.
        bookmarks: Optional bookmark(s) for causal chaining.

    Returns:
        List of records (dicts if as_dict=True).

    Raises:
        Exception: Any driver/session/run exceptions are surfaced to caller.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("cypher_query: 'query' must be a non-empty string")

    drv: Optional[AsyncDriver] = driver or get_driver()
    if drv is None:
        raise RuntimeError("cypher_query: Neo4j driver is not initialized")

    db = database or NEO4J_DATABASE
    safe_params = neo_safe_params(params)

    session_kwargs: Dict[str, Any] = {"database": db}
    if bookmarks is not None:
        session_kwargs["bookmarks"] = bookmarks

    run_kwargs: Dict[str, Any] = {}
    if timeout_s is not None:
        run_kwargs["timeout"] = timeout_s

    records: List[Any] = []
    async with drv.session(**session_kwargs) as neo_session:
        result = await neo_session.run(query, safe_params, **run_kwargs)
        if as_dict:
            async for rec in result:
                records.append(rec.data())
        else:
            async for rec in result:
                records.append(rec)
    return records


async def cypher_query_one(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    driver: Optional[AsyncDriver] = None,
    database: Optional[str] = None,
    as_dict: bool = True,
    timeout_s: Optional[float] = None,
    bookmarks: Optional[Sequence[str] | str] = None,
) -> Any | None:
    """Execute and return the first record (or None)."""
    rows = await cypher_query(
        query,
        params,
        driver=driver,
        database=database,
        as_dict=as_dict,
        timeout_s=timeout_s,
        bookmarks=bookmarks,
    )
    return rows[0] if rows else None


async def cypher_query_scalar(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    driver: Optional[AsyncDriver] = None,
    database: Optional[str] = None,
    timeout_s: Optional[float] = None,
    bookmarks: Optional[Sequence[str] | str] = None,
    default: Any = None,
) -> Any:
    """Execute and return the first column of the first row (or `default`)."""
    row = await cypher_query_one(
        query,
        params,
        driver=driver,
        database=database,
        as_dict=False,  # return neo4j.Record
        timeout_s=timeout_s,
        bookmarks=bookmarks,
    )
    if row is None:
        return default
    try:
        return row[0]
    except Exception:
        # Fallback to dict access if driver returns a mapping-like row
        try:
            data = row.data()
            return next(iter(data.values())) if data else default
        except Exception:
            return default
