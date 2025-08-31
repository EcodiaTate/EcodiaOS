from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

graph_export_router = APIRouter()

# Lightweight WM index access
try:
    from systems.qora.wm.indexer import _index  # type: ignore
except Exception:  # pragma: no cover
    _index = None


class GraphExportRequest(BaseModel):
    fmt: str = Field("dot", description="dot or json")


class GraphExportResponse(BaseModel):
    ok: bool
    dot: str | None = None
    json_data: dict[str, Any] | None = Field(None, alias="json")  # <-- Renamed field


@graph_export_router.post("/graph_export", response_model=GraphExportResponse)
async def graph_export(req: GraphExportRequest) -> GraphExportResponse:
    if _index is None:
        raise HTTPException(status_code=501, detail="WM index not available")
    idx = _index() or {}
    nodes: dict[str, dict[str, Any]] = idx.get("nodes", {}) or {}
    edges: list[tuple[str, str, str]] = idx.get("edges", []) or []
    if req.fmt == "json":
        return GraphExportResponse(ok=True, json_data={"nodes": nodes, "edges": edges})
    # dot
    lines = ["digraph WM {", "  rankdir=LR;", '  node [shape=box, fontname="Arial"];']
    for fq, meta in nodes.items():
        label = fq.replace('"', '\\"')
        lines.append(f'  "{fq}" [label="{label}"];')
    for src, dst, et in edges:
        etq = et.replace('"', '\\"')
        lines.append(f'  "{src}" -> "{dst}" [label="{etq}"];')
    lines.append("}")
    return GraphExportResponse(ok=True, dot="\n".join(lines))
