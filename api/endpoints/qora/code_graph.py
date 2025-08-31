# api/endpoints/qora/code_graph.py
# --- AMBITIOUS UPGRADE (ADDED GOAL-ORIENTED CONTEXT ENDPOINT) ---
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# Now importing the full get_dossier
from systems.qora.core.code_graph.dossier_service import (
    _get_semantic_neighbors,
    _get_structural_neighbors,
    get_dossier,
)
from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query


code_graph_router = APIRouter()

### --- API Schemas --- ###

class SemanticSearchRequest(BaseModel):
    query_text: str = Field(..., description="The natural language query to search for similar code.")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return.")

class CallGraphResponse(BaseModel):
    ok: bool
    target_fqn: str
    callers: list[dict]
    callees: list[dict]
    siblings: list[dict]
    file: dict | None

### --- Endpoints --- ###

@code_graph_router.get("/visualize")
async def get_full_graph_visualization_query() -> dict[str, str]:
    """
    Returns the comprehensive Cypher query for visualizing the full code graph,
    including files, functions, classes, libraries, and all their relationships.
    """
    query = """
    MATCH (n)
    WHERE n:CodeFile OR n:Function OR n:Class OR n:Library
    OPTIONAL MATCH p=(n)-[r]-(m)
    WHERE m:CodeFile OR m:Function OR n:Class OR n:Library
    RETURN n, r, m
    LIMIT 200
    """ 
    return {
        "description": "Run this query in your Neo4j Browser to visualize the enriched code graph. It will show all code elements, libraries, and their connections.",
        "query": query
    }

@code_graph_router.post("/semantic_search")
async def semantic_search(req: SemanticSearchRequest) -> dict[str, Any]:
    """
    Performs a vector-based semantic search across all indexed code functions and classes.
    """
    try:
        embedding = await get_embedding(req.query_text) 
        search_results = await _get_semantic_neighbors(embedding, req.top_k)
        return {"ok": True, "hits": search_results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic search failed: {e!r}")

@code_graph_router.get("/call_graph", response_model=CallGraphResponse)
async def get_call_graph(fqn: str = Query(..., description="The FQN of the target, e.g., 'path/to/file.py::my_func'")) -> CallGraphResponse:
    """
    Retrieves the direct callers and callees for a specific function from the Code Graph.
    """
    try:
        graph_data = await _get_structural_neighbors(fqn)
        if not graph_data:
            raise HTTPException(status_code=404, detail=f"FQN '{fqn}' not found in the Code Graph.")
            
        return CallGraphResponse(
            ok=True,
            target_fqn=fqn,
            callers=graph_data.get("callers", []),
            callees=graph_data.get("callees", []),
            siblings=graph_data.get("siblings", []),
            file=graph_data.get("file")
        ) 
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Call graph retrieval failed: {e!r}")

@code_graph_router.post("/goal_oriented_context")
async def get_goal_context(req: SemanticSearchRequest) -> dict[str, Any]:
    """
    NEW: Finds the most relevant code entities for a high-level goal and returns
    a collection of dossiers for them. This is a proactive context-gathering tool.
    """
    try:
        embedding = await get_embedding(req.query_text)
        # Find the top K most relevant code nodes
        search_results = await _get_semantic_neighbors(embedding, req.top_k)
        if not search_results:
            return {"ok": True, "relevant_dossiers": []}

        # For each hit, build its full dossier
        dossier_tasks = [
            get_dossier(target_fqn=hit['fqn'], intent=req.query_text)
            for hit in search_results
        ]
        dossiers = await asyncio.gather(*dossier_tasks)
        
        # Filter out any dossiers that had errors
        successful_dossiers = [d for d in dossiers if "error" not in d]
        
        return {"ok": True, "relevant_dossiers": successful_dossiers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get goal context: {e!r}")