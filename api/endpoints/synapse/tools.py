from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

tools_router = APIRouter()


@tools_router.get("/tools")
@tools_router.get("/tools/")
async def list_tools(
    q: str | None = Query(default=None, description="Substring filter on tool name"),
    names_only: bool = Query(default=False, description="If true, return just the names"),
) -> dict[str, Any]:
    # Pull the canonical registry and merged specs
    from systems.simula.agent.tool_registry import TOOLS as REG

    try:
        from systems.simula.agent.tool_specs import get_tool_specs

        specs_list = get_tool_specs()
        specs_by_name = {s["name"]: s for s in specs_list if isinstance(s, dict) and "name" in s}
    except Exception:
        specs_by_name = {}

    # Build response
    names: list[str] = sorted(REG.keys())
    if q:
        ql = q.lower()
        names = [n for n in names if ql in n.lower()]

    if names_only:
        return {"status": "ok", "count": len(names), "names": names}

    tools: list[dict[str, Any]] = []
    for n in names:
        item: dict[str, Any] = {"name": n}
        if n in specs_by_name:
            item["spec"] = specs_by_name[n]
        tools.append(item)

    return {"status": "ok", "count": len(tools), "tools": tools}
