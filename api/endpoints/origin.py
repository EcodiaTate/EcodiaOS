# D:\EcodiaOS\api\endpoints\origin.py
from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from systems.qora.core.origin_ingest import (
    create_edges_from,
    create_origin_node,
    ensure_origin_indices,
    force_origin_label,
    resolve_event_or_internal_id,
    search_mixed,
)

ADMIN_TOKEN = None  # loaded at startup
CONTRIBUTOR = "Tate"

router = APIRouter()


# FIXED: Consolidated multi-line type hint
def check_admin(x_admin_token: str | None = Header(None)):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="Admin token not configured")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


class OriginIn(BaseModel):
    title: str
    # FIXED: Consolidated multi-line attribute
    summary: str | None = ""
    what: str
    # FIXED: Consolidated multi-line attribute
    where: str | None = None
    when: str | None = None  # ISO
    tags: list[str] = Field(default_factory=list)
    # FIXED: Consolidated multi-line attribute
    alias: str | None = None  # optional alias for immediate edge refs


class OriginCreated(BaseModel):
    event_id: str
    node_id: int


class SearchIn(BaseModel):
    query: str
    k: int = 10


class SearchHit(BaseModel):
    id: str
    labels: list[str]
    # FIXED: Consolidated multi-line attribute
    title: str | None = None
    summary: str | None = None
    # FIXED: Consolidated multi-line attribute
    score: float | None = None


class EdgeIn(BaseModel):
    to_id: str
    label: str
    # FIXED: Consolidated multi-line attribute
    note: str | None = ""


class EdgeCreateIn(BaseModel):
    from_id: str
    edges: list[EdgeIn]


class BatchCSVIn(BaseModel):
    csv: str  # literal CSV text


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    # FIXED: Consolidated multi-line statement
    sep = ";" if ";" in raw else ","
    parts = [p.strip().lstrip("#") for p in raw.split(sep)]
    out, seen = [], set()
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


@router.on_event("startup")
async def _startup():
    from os import getenv

    global ADMIN_TOKEN, CONTRIBUTOR
    ADMIN_TOKEN = getenv("ADMIN_API_TOKEN", None)
    # FIXED: Consolidated multi-line statement
    CONTRIBUTOR = getenv("ORIGIN_CONTRIBUTOR", CONTRIBUTOR)
    await ensure_origin_indices()


@router.post("/origin/node", response_model=OriginCreated)
async def post_node(payload: OriginIn, _: bool = Depends(check_admin)):
    ev_id, node_id = await create_origin_node(
        contributor=CONTRIBUTOR,
        title=payload.title,
        summary=payload.summary or "",
        what=payload.what or "",
        where=payload.where,
        when=payload.when,
        tags=payload.tags or [],
    )
    try:
        await force_origin_label(node_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enforce :Origin label: {e}")
    # optional: alias is NOT stored here;
    # alias belongs to CSV batch map. (You can persist if you want.)
    return OriginCreated(event_id=ev_id, node_id=node_id)


@router.post("/origin/search", response_model=dict[str, list[SearchHit]])
async def post_search(payload: SearchIn, _: bool = Depends(check_admin)):
    hits = await search_mixed(payload.query, payload.k)
    return {"results": [SearchHit(**h) for h in hits]}


@router.post("/origin/edges")
async def post_edges(payload: EdgeCreateIn, _: bool = Depends(check_admin)):
    from_id_resolved = await resolve_event_or_internal_id(payload.from_id)
    edges = [{"to_id": e.to_id, "label": e.label, "note": e.note or ""} for e in payload.edges]
    created = await create_edges_from(from_id_resolved, edges)
    return {"edges_created": created}


@router.post("/origin/batch_csv")
async def post_batch_csv(payload: BatchCSVIn, _: bool = Depends(check_admin)):
    """
    CSV headers: title,summary,what,where,when,tags,edges,alias
    - alias is optional; use @alias:name in edges.to_id to reference nodes created in the same file.
    """
    f = io.StringIO(payload.csv)
    reader = csv.DictReader(f)

    rows = [row for row in reader]
    created = 0
    edges_created = 0
    errors: list[dict[str, Any]] = []

    row_event_ids: dict[int, str] = {}
    alias_map: dict[str, str] = {}

    # PASS 1: create nodes
    for i, row in enumerate(rows, start=2):
        title = (row.get("title") or "").strip()
        if not title:
            continue

        summary = row.get("summary") or ""
        what = row.get("what") or ""
        where = (row.get("where") or None) or None
        when = (row.get("when") or None) or None
        alias = (row.get("alias") or "").strip()
        tags = _parse_tags(row.get("tags"))

        try:
            ev_id, node_id = await create_origin_node(
                contributor=CONTRIBUTOR,
                title=title,
                summary=summary,
                what=what,
                where=where,
                when=when,
                tags=tags,
            )
            await force_origin_label(node_id)
            created += 1
            row_event_ids[i] = ev_id
            if alias:
                alias_map[alias] = ev_id
        except Exception as e:
            errors.append({"row": i, "title": title, "error": f"create_origin_node: {e}"})

    # PASS 2: edges (resolve @alias:)
    for i, row in enumerate(rows, start=2):
        ev_id = row_event_ids.get(i)
        if not ev_id:
            continue

        edges_json = (row.get("edges") or "").strip()
        if not edges_json:
            continue

        try:
            arr = json.loads(edges_json)
            if not isinstance(arr, list):
                arr = []
        except Exception as e:
            errors.append(
                {"row": i, "title": (row.get("title") or ""), "error": f"edges JSON parse: {e}"},
            )
            arr = []

        if not arr:
            continue

        try:
            resolved_from = await resolve_event_or_internal_id(ev_id)
            edges_payload = []
            for e in arr:
                if not isinstance(e, dict):
                    continue
                raw_to = (e.get("to_id") or "").strip()
                label = (e.get("label") or "").strip()
                note = (e.get("note") or "").strip()
                if not raw_to or not label:
                    continue
                if raw_to.startswith("@alias:"):
                    alias_name = raw_to.split(":", 1)[1]
                    mapped = alias_map.get(alias_name)
                    if not mapped:
                        continue
                    raw_to = mapped
                edges_payload.append({"to_id": raw_to, "label": label, "note": note})

            if edges_payload:
                edges_created += await create_edges_from(resolved_from, edges_payload)

        except Exception as e:
            errors.append(
                {"row": i, "title": (row.get("title") or ""), "error": f"create_edges_from: {e}"},
            )

    return {
        "created": created,
        "edges_created": edges_created,
        "errors": errors,
        "aliases": alias_map,
    }