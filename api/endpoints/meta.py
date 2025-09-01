# api/endpoints/meta.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from core.utils.neo.cypher_query import cypher_query

meta_router = APIRouter()

# highlight-start
def _alias_from_path(path: str) -> str:
    """
    Helper to derive a canonical ALIAS from a REST path.
    e.g., "/simula/jobs/codegen" -> "SIMULA_JOBS_CODEGEN"
    """
    if not path:
        return "UNKNOWN"
    # Drop path parameters like {driver_name}
    clean_path = path.split("{")[0]
    return clean_path.strip("/").upper().replace("/", "_").replace("-", "_")

def _generate_endpoint_map(request: Request) -> dict[str, Any]:
    """
    Inspects the running FastAPI app to build the alias-to-path map.
    This is the authoritative source for the endpoint registry.
    """
    aliases: dict[str, str] = {}
    for route in request.app.routes:
        # We only care about APIRoutes, not sub-apps or websockets
        if hasattr(route, "path") and route.path not in ["/openapi.json", "/docs", "/redoc"]:
             alias = _alias_from_path(route.path)
             if alias and alias not in aliases:
                aliases[alias] = route.path
    return {"aliases": aliases}
# highlight-end

@meta_router.get("/neo")
async def health_neo():
    try:
        rows = await cypher_query("RETURN 1 AS ok")
        ok = bool(rows and rows[0].get("ok"))
        return {"status": "ok" if ok else "degraded", "ok": ok}
    except Exception as e:
        return {"status": "error", "ok": False, "error": str(e)}

@meta_router.get("/health")
async def health():
    return {"status": "ok"}


# highlight-start
@meta_router.get("/meta/endpoints")
async def meta_endpoints(request: Request):
    """
    Returns a JSON snapshot of all discovered endpoint aliases.
    This is the source of truth for the LiveEndpointRegistry.
    """
    return _generate_endpoint_map(request)

@meta_router.get("/meta/endpoints.txt", response_class=PlainTextResponse)
async def meta_endpoints_text(request: Request):
    """Returns a human-readable text report of the endpoint mapping."""
    data = _generate_endpoint_map(request)
    aliases = data.get("aliases", {})
    if not aliases:
        return "No discoverable endpoints found."

    width = max((len(k) for k in aliases.keys()), default=8) + 2
    lines = [f"{'ALIAS'.ljust(width)}PATH"]
    lines.append(f"{'-'*width}{'-'*4}")
    for k in sorted(aliases.keys()):
        lines.append(f"{k.ljust(width)}{aliases[k]}")
    return "\n".join(lines)
# highlight-end