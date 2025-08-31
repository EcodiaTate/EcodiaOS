# D:\EcodiaOS\api\endpoints\meta.py
# 
# systems/health/app_health.py
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import endpoints_report_str, endpoints_snapshot

meta_router = APIRouter()


@meta_router.get("/neo")
async def health_neo():
    """
    Basic Neo4j liveness: runs a trivial query.
    Uses driverless cypher_query() which resolves the AsyncDriver internally.
    """
    try:
        rows = await cypher_query("RETURN 1 AS ok", {})
        ok = bool(rows and (rows[0].get("ok") in (1, True)))
        return {
            "status": "ok" if ok else "degraded",
            "ok": ok,
            "message": "EcodiaOS... the mind of the future!",
 
        }
    except Exception as e:
        return {"status": "error", "ok": False, "error": str(e)}


@meta_router.get("/vector")
async def health_vector():
    """
    Reports how many VECTOR indexes exist (Neo4j 5+).
    Falls back to CALL db.indexes() if SHOW INDEXES isn't available.
    """
    try:
        # Preferred for Neo4j 5
        try:
            rows = await cypher_query(
                """
                SHOW INDEXES YIELD name, type
                WHERE type = 'VECTOR'
      
                RETURN count(*) AS n
                """,
                {},
            )
        except Exception:
            # Fallback for older compatibility
            rows = await cypher_query(
   
                """
                CALL db.indexes() YIELD name, type
                WITH name, type WHERE type = 'VECTOR'
                RETURN count(*) AS n
                """,
          
                {},
            )

        n = int(rows[0]["n"]) if rows and "n" in rows[0] else 0
        return {"vector_indexes": n, "status": "ok"}
    except Exception as e:
        return {
            "vector_indexes": None,
            "status": "error",
          
            "error": str(e),
            "hint": "Ensure Neo4j 5+, vector indexes created, and async driver initialized.",
        }


@meta_router.get("/")
async def health_root():
    return {"status": "ok", "message": "EcodiaOS... the mind of the future!"}


@meta_router.get("/health")
async def health():
    # Simple app-level health endpoint (no DB touch)
    return {"status": "200OK ;)"}


@meta_router.get("/meta/endpoints")
async def meta_endpoints():
    return await endpoints_snapshot()


@meta_router.get("/meta/endpoints.txt", response_class=PlainTextResponse)
async def meta_endpoints_text():
    # FastAPI will return text/plain automatically from a str
    return await endpoints_report_str()