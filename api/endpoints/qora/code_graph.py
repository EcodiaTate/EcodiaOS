# --- GOAL-ORIENTED CONTEXT & UTILITIES ---
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.llm.embeddings_gemini import get_embedding

# Semantic/structural utilities + dossier builder
from systems.qora.core.code_graph.dossier_service import (
    _get_semantic_neighbors,
    _get_structural_neighbors,
    get_dossier,
)

code_graph_router = APIRouter(tags=["qora", "code_graph"])

# ---------- Schemas ----------


class SemanticSearchRequest(BaseModel):
    query_text: str = Field(..., description="Natural-language goal / query for relevant code.")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return.")


class CallGraphResponse(BaseModel):
    ok: bool
    target_fqn: str
    callers: list[dict]
    callees: list[dict]
    siblings: list[dict]
    file: dict | None


# ---------- Endpoints ----------


@code_graph_router.get("/visualize")
async def get_full_graph_visualization_query(
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, str]:
    """
    Returns a Cypher you can paste in Neo4j Browser to visualize the code graph.
    Includes CodeFile, Function, Class, Library and their relationships.
    """
    # Fixed WHERE typo: second WHERE must filter on 'm', not 'n'
    query = f"""
    MATCH (n)
    WHERE n:CodeFile OR n:Function OR n:Class OR n:Library
    OPTIONAL MATCH p=(n)-[r]-(m)
    WHERE m:CodeFile OR m:Function OR m:Class OR m:Library
    RETURN DISTINCT n, r, m
    LIMIT {limit}
    """
    return {
        "description": "Run this in Neo4j Browser to visualize all code nodes and library links.",
        "query": query.strip(),
    }


@code_graph_router.post("/semantic_search")
async def semantic_search(req: SemanticSearchRequest) -> dict[str, Any]:
    """
    Vector-based semantic search across indexed code symbols.
    """
    q = (req.query_text or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query_text must not be empty")
    try:
        embedding = await get_embedding(q)
        hits = await _get_semantic_neighbors(embedding, req.top_k)
        return {"ok": True, "hits": hits or []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"semantic_search_error: {e!r}")


@code_graph_router.get("/call_graph", response_model=CallGraphResponse)
async def get_call_graph(
    fqn: str = Query(..., description="FQN like 'path/to/file.py::Class::func' or '...::func'"),
) -> CallGraphResponse:
    """
    Retrieves direct callers/callees and sibling symbols for an FQN.
    """
    f = (fqn or "").strip()
    if not f:
        raise HTTPException(status_code=400, detail="fqn must not be empty")
    try:
        graph = await _get_structural_neighbors(f)
        if not graph:
            raise HTTPException(status_code=404, detail=f"FQN '{f}' not found in the Code Graph.")
        return CallGraphResponse(
            ok=True,
            target_fqn=f,
            callers=graph.get("callers", []),
            callees=graph.get("callees", []),
            siblings=graph.get("siblings", []),
            file=graph.get("file"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"call_graph_error: {e!r}")


@code_graph_router.post("/goal_oriented_context")
async def get_goal_context(req: SemanticSearchRequest) -> dict[str, Any]:
    """
    Finds the most relevant code entities for a high-level goal (semantic KNN),
    then builds a dossier for each hit.
    """
    q = (req.query_text or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query_text must not be empty")
    try:
        embedding = await get_embedding(q)
        hits = await _get_semantic_neighbors(embedding, req.top_k)
        if not hits:
            return {"ok": True, "relevant_dossiers": []}

        # Build dossiers for each FQN; intent = the goal text for extra signal
        tasks = [get_dossier(target_fqn=h["fqn"], intent=q) for h in hits if "fqn" in h]
        dossiers = await asyncio.gather(*tasks, return_exceptions=True)

        good: list[dict[str, Any]] = []
        for d in dossiers:
            if isinstance(d, Exception):
                # Keep going; surface partials
                continue
            if isinstance(d, dict) and not d.get("error") and d.get("status") != "error":
                good.append(d)

        return {"ok": True, "relevant_dossiers": good}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"goal_context_error: {e!r}")
