# api/endpoints/qora/tools_catalog.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from core.utils.neo.cypher_query import cypher_query

catalogue_router = APIRouter()


@catalogue_router.get("/")
async def list_tools(
    agent: str | None = Query(default=None, description="Filter by agent label"),
    capability: str | None = Query(default=None, description="Filter by capability"),
    safety_max: int | None = Query(default=None, ge=0, le=5),
) -> dict[str, Any]:
    """
    Returns a list of LLM-ready tool specs from Neo.
    Qora Patrol should populate SystemFunction nodes with tool_* properties.
    """
    q = """
    MATCH (fn:SystemFunction)
    WHERE (fn.tool_name) IS NOT NULL
      AND ( $agent IS NULL OR fn.tool_agent IN [$agent, "*"] )
      AND ( $safety_max IS NULL OR coalesce(fn.safety_tier, 3) <= $safety_max )
      AND ( $capability IS NULL OR ANY(c IN coalesce(fn.tool_caps,[]) WHERE c = $capability) )
    RETURN fn.tool_name AS name,
           coalesce(fn.tool_desc, fn.docstring, "") AS description,
           coalesce(fn.tool_params_schema, {}) AS parameters,
           coalesce(fn.tool_outputs_schema, {}) AS outputs,
           coalesce(fn.tool_agent, "*") AS agent,
           coalesce(fn.safety_tier, 3) AS safety_tier,
           coalesce(fn.allow_external, false) AS allow_external,
           fn.uid AS x_uid
    ORDER BY name
    """
    rows = await cypher_query(
        q,
        {"agent": agent, "capability": capability, "safety_max": safety_max},
    )
    return {"ok": True, "tools": rows or []}
