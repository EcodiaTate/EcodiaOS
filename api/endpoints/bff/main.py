# api/endpoints/bff/main.py
# FINAL VERSION: Backend-for-Frontend (BFF) for the EcodiaOS Ecosystem Console
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field

# Direct Cypher access for complex aggregations not exposed by service APIs
from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.atune.control.affect import AffectiveState

logger = logging.getLogger(__name__)

# IMPORTANT: avoid governance recursion on internal HTTP calls
IMMUNE_HEADER = "x-ecodia-immune"
IMMUNE_HEADERS = {IMMUNE_HEADER: "1"}

bff_router = APIRouter(prefix="/bff", tags=["BFF Ecosystem Console"])


# ----------------------------------------------------------------------
# Shared
# ----------------------------------------------------------------------
async def get_client():
    return await get_http_client()


class ApiProxyRequest(BaseModel):
    method: str = Field(..., description="HTTP method (e.g., 'GET', 'POST')")
    path: str = Field(..., description="Absolute URL or path (e.g., '/synapse/metrics/leaderboard')")
    data: dict | list | None = Field(None, description="Request body for POST/PUT/PATCH")


# ======================================================================
# 1) Universal Search & Decision Journey
# ======================================================================
@bff_router.get("/search", summary="Universal search across EcodiaOS")
async def universal_search(q: str):
    """Aggregates search results from multiple systems."""
    if len(q) < 3:
        return []

    async def search_conflicts():
        try:
            client = await get_client()
            res = await client.get(f"{ENDPOINTS.EVO_CONFLICTS}/open", headers=IMMUNE_HEADERS)
            res.raise_for_status()
            data = res.json()
            items = data if isinstance(data, list) else data.get("items", [])
            out = []
            for c in items:
                desc = c.get("description") or c.get("summary") or ""
                cid = c.get("conflict_id") or c.get("id") or c.get("uuid")
                if cid and q.lower() in desc.lower():
                    out.append({"id": cid, "type": "Conflict", "label": desc})
            return out
        except Exception:
            return []

    results = await asyncio.gather(search_conflicts())
    return [item for sublist in results for item in sublist]


@bff_router.get("/decision_journey/{decision_id}", summary="Get context for a decision journey")
async def get_decision_journey(decision_id: str):
    """Aggregates artifacts related to a single decision ID."""
    async def get_conflict_summary():
        try:
            client = await get_client()
            # Often decision_id == conflict_id in our flows
            res = await client.get(f"{ENDPOINTS.EVO_CONFLICTS}/{decision_id}", headers=IMMUNE_HEADERS)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception:
            return None

    conflict_data = await get_conflict_summary()
    return {
        "decision_id": decision_id,
        "conflict": conflict_data,
        # TODO: graft Atune/Nova/Equor traces as they mature
    }


# ======================================================================
# 2) Generic Proxy
# ======================================================================
@bff_router.post("/proxy", summary="Generic proxy for API Explorer")
async def api_proxy(payload: ApiProxyRequest, original_request: Request):
    client = await get_client()

    # Allow absolute URLs; otherwise resolve against this host
    if payload.path.startswith("http://") or payload.path.startswith("https://"):
        full_url = payload.path
    else:
        base_url = f"{original_request.url.scheme}://{original_request.url.netloc}"
        # ensure a single slash
        if not payload.path.startswith("/"):
            payload.path = "/" + payload.path
        full_url = f"{base_url}{payload.path}"

    try:
        response = await client.request(
            method=payload.method.upper(),
            url=full_url,
            json=payload.data if payload.data is not None else None,
            headers=IMMUNE_HEADERS,
            timeout=15.0,
        )
        response.raise_for_status()
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text
    except Exception as e:
        logger.exception("BFF API proxy failed for path: %s", payload.path)
        error_detail = getattr(getattr(e, "response", None), "text", str(e))
        raise HTTPException(status_code=502, detail=f"API request to '{payload.path}' failed: {error_detail}")


# ======================================================================
# 3) Observability Wing (Atune & Qora)
# ======================================================================
observability_router = APIRouter(prefix="/observability", tags=["BFF Observability"])

@observability_router.get("/atune/status", summary="Get Atune's real-time status")
async def get_atune_status():
    client = await get_client()
    try:
        response = await client.get(ENDPOINTS.ATUNE_META_STATUS, headers=IMMUNE_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch Atune status: {e!r}")

@observability_router.post("/atune/modulate", summary="Modulate Atune's affective state")
async def modulate_atune_affect(affect_override: AffectiveState):
    client = await get_client()
    try:
        response = await client.post(
            ENDPOINTS.ATUNE_COGNITIVE_CYCLE,
            json={"events": [], "affect_override": affect_override.model_dump()},
            headers=IMMUNE_HEADERS,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not modulate Atune: {e!r}")


# ======================================================================
# 4) Qora Intelligence Router
# ======================================================================
qora_router = APIRouter(prefix="/qora", tags=["BFF Qora Intelligence"])

class AnnotateDiffRequest(BaseModel):
    diff: str

@qora_router.post("/annotate_diff", summary="Annotate a PR diff")
async def annotate_diff(req: AnnotateDiffRequest):
    client = await get_client()
    try:
        response = await client.post(
            ENDPOINTS.QORA_ANNOTATE_DIFF,
            json=req.model_dump(),
            headers=IMMUNE_HEADERS,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not annotate diff: {e!r}")


# ======================================================================
# 5) Axon Driver Lifecycle Router
# ======================================================================
axon_router = APIRouter(prefix="/axon", tags=["BFF Axon Drivers"])

class SynthesizeRequest(BaseModel):
    driver_name: str
    api_spec_url: str

@axon_router.get("/drivers", summary="List all drivers and their states")
async def list_drivers():
    client = await get_client()
    try:
        response = await client.get(ENDPOINTS.AXON_PROBECRAFT_DRIVERS, headers=IMMUNE_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not list Axon drivers: {e!r}")

@axon_router.get("/scorecards", summary="Get driver performance scorecards")
async def get_scorecards():
    client = await get_client()
    try:
        response = await client.get(ENDPOINTS.AXON_PROBECRAFT_SCORECARDS, headers=IMMUNE_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not get scorecards: {e!r}")

@axon_router.post("/synthesize", summary="Synthesize a new driver")
async def synthesize_driver(req: SynthesizeRequest):
    client = await get_client()
    try:
        response = await client.post(
            ENDPOINTS.AXON_PROBECRAFT_SYNTHESIZE,
            json=req.model_dump(),
            headers=IMMUNE_HEADERS,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not synthesize driver: {e!r}")


# ======================================================================
# 6) Synapse BFF Router (matches UI: /bff/synapse/*)
# ======================================================================
synapse_bff = APIRouter(prefix="/synapse", tags=["BFF Synapse"])

@synapse_bff.get("/metrics/leaderboard", summary="Get Synapse Policy Arm Leaderboard")
async def synapse_leaderboard(
    days: int = Query(7, ge=1, le=90),
    top_k: int = Query(12, ge=1, le=200),
):
    try:
        client = await get_client()
        # Forward both days & top_k
        response = await client.get(
            ENDPOINTS.SYNAPSE_METRICS_LEADERBOARD,
            params={"days": days, "top_k": top_k},
            headers=IMMUNE_HEADERS,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch Synapse leaderboard: {e!r}")

@synapse_bff.post("/registry/reload", status_code=202, summary="Trigger a hot-reload of the Synapse Arm Registry")
async def synapse_reload_registry():
    try:
        client = await get_client()
        response = await client.post(ENDPOINTS.SYNAPSE_REGISTRY_RELOAD, json={}, headers=IMMUNE_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not trigger registry reload: {e!r}")

@synapse_bff.get("/tools", summary="List tools from Synapse registry")
async def synapse_tools(names_only: bool = Query(False)):
    try:
        client = await get_client()
        response = await client.get(
            ENDPOINTS.SYNAPSE_TOOLS,
            params={"names_only": str(names_only).lower()},
            headers=IMMUNE_HEADERS,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch Synapse tools: {e!r}")

class ArmPreference(BaseModel):
    winner: str
    loser: str
    source: Optional[str] = "ui"

@synapse_bff.post("/ingest/preference", summary="Record an Arm-vs-Arm preference")
async def synapse_ingest_preference(pref: ArmPreference):
    try:
        client = await get_client()
        response = await client.post(
            f"{ENDPOINTS.SYNAPSE_INGEST_PREFERENCE}",
            json=pref.model_dump(),
            headers=IMMUNE_HEADERS,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not submit preference: {e!r}")


# ======================================================================
# 7) Governance Wing (legacy/governance URLs kept for compatibility)
# ======================================================================
governance_router = APIRouter(tags=["BFF Governance"])

# Keep these for older UI calls that still hit /bff/governance/*
@governance_router.get("/synapse/leaderboard", summary="(Compat) Synapse Leaderboard")
async def get_synapse_leaderboard(days: int = Query(7, ge=1, le=90), top_k: int = Query(12, ge=1, le=200)):
    return await synapse_leaderboard(days=days, top_k=top_k)

@governance_router.post("/synapse/reload_registry", status_code=202, summary="(Compat) Reload Arm Registry")
async def reload_synapse_registry():
    return await synapse_reload_registry()

@governance_router.get("/synapse/arms", summary="List all Policy Arms from the graph")
async def get_synapse_arms():
    try:
        query = """
        MATCH (p:PolicyArm)
        RETURN p.arm_id AS arm_id,
               p.mode   AS mode,
               p.policy_graph_json AS policy_graph
        ORDER BY p.created_at DESC
        LIMIT 200
        """
        results = await cypher_query(query, {})
        return results or []
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not list Synapse arms: {e!r}")

# Evo passthroughs (used by search/journey)
@governance_router.get("/evo/conflicts", summary="Get open conflicts from Evo")
async def get_open_conflicts(limit: int | None = Query(default=50, ge=1, le=200)):
    try:
        client = await get_client()
        response = await client.get(f"{ENDPOINTS.EVO_CONFLICTS}", params={"limit": limit}, headers=IMMUNE_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch open conflicts: {e!r}")

@governance_router.get("/evo/conflict/{conflict_id}", summary="Get detailed conflict view from Evo")
async def get_conflict_details(conflict_id: str = Path(...)):
    try:
        client = await get_client()
        conflict_res = await client.get(f"{ENDPOINTS.EVO_CONFLICTS}/{conflict_id}", headers=IMMUNE_HEADERS)
        conflict_res.raise_for_status()
        return {"conflict": conflict_res.json()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch conflict details: {e!r}")

@governance_router.get("/qora/tools", summary="Get the Qora Tool Catalog")
async def get_qora_tools():
    try:
        client = await get_client()
        response = await client.get(ENDPOINTS.QORA_CATALOG, headers=IMMUNE_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch Qora tool catalog: {e!r}")


# ======================================================================
# 8) Operations Wing (Simula & Unity)
# ======================================================================
operations_router = APIRouter(prefix="/operations", tags=["BFF Operations"])

@operations_router.get("/unity/deliberations", summary="List historical Unity deliberations")
async def list_unity_deliberations(limit: int = Query(20, ge=1, le=100)):
    try:
        query = """
        MATCH (s:DeliberationSession)
        RETURN s.id AS id, s.topic AS topic, s.status AS status, s.created_at AS created_at
        ORDER BY s.created_at DESC
        LIMIT $limit
        """
        results = await cypher_query(query, {"limit": limit})
        return results or []
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not list Unity deliberations: {e!r}")

@operations_router.get("/unity/deliberation/{session_id}", summary="Get a full Unity deliberation transcript")
async def get_unity_deliberation(session_id: str):
    try:
        query = """
        MATCH (s:DeliberationSession {id: $session_id})
        OPTIONAL MATCH (s)-[:HAS_TRANSCRIPT]->(tc:TranscriptChunk)
        WITH s, tc ORDER BY tc.turn ASC
        WITH s, collect({ turn: tc.turn, role: tc.role, content: tc.content }) AS transcript
        OPTIONAL MATCH (s)-[:RESULTED_IN]->(v:Verdict)
        RETURN s { .*, spec: apoc.convert.fromJsonMap(s.spec) } AS session,
               transcript,
               v { .*, outcome: v.outcome, confidence: v.confidence, uncertainty: v.uncertainty, dissent: v.dissent } AS verdict
        """
        results = await cypher_query(query, {"session_id": session_id})
        if not results:
            raise HTTPException(status_code=404, detail="Deliberation session not found.")
        return results[0]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch deliberation: {e!r}")


# --- Main BFF Router mounts ---
bff_router.include_router(observability_router)
bff_router.include_router(synapse_bff)        # <--- UI-friendly /bff/synapse/*
bff_router.include_router(governance_router)  # legacy /bff/governance/*
bff_router.include_router(operations_router)
bff_router.include_router(qora_router)
bff_router.include_router(axon_router)
