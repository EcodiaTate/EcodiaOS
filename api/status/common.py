# api/status/common.py
from __future__ import annotations
import asyncio, os, time
from typing import Dict, Iterable, List, Optional, Tuple
from fastapi import APIRouter, Response
from core.utils.net_api import ENDPOINTS, get_http_client

Json = Dict[str, object]
CheckKey = str

SERVICE_CHECKS: Dict[str, Dict[str, List[CheckKey]]] = {
    "atune":  {"required": ["ATUNE_ROUTE"], "optional": ["AXON_ACT", "SYNAPSE_SELECT_ARM"]},
    "synapse":{"required": ["SYNAPSE_SELECT_ARM", "SYNAPSE_INGEST_OUTCOME"], "optional": ["SYNAPSE_REGISTRY_RELOAD","SYNAPSE_LEADERBOARD"]},
    "unity":  {"required": ["UNITY_DELIBERATE"], "optional": ["SYNAPSE_SELECT_ARM","EQUOR_ATTEST"]},
    "equor":  {"required": ["EQUOR_ATTEST"], "optional": []},
    "qora":   {"required": ["QORA_ARCH_HEALTH"], "optional": ["QORA_ARCH_EXECUTE_QUERY"]},
    "simula": {"required": ["SIMULA_JOBS_CODEGEN"], "optional": ["SIMULA_RUNS_LIST"]},
    "evo":    {"required": ["ATUNE_ROUTE"], "optional": ["NOVA_PROPOSE"]},
    "axon":   {"required": ["AXON_ACT"], "optional": ["AXON_CAPABILITIES"]},
}

def _resolve_endpoint(key: str) -> Optional[str]:
    try:
        url = getattr(ENDPOINTS, key)
        if url: return str(url)
    except Exception:
        pass
    try:
        return str(ENDPOINTS[key])  # type: ignore[index]
    except Exception:
        return None

async def _probe(key: str, timeout_s: float = 1.5) -> Json:
    url = _resolve_endpoint(key)
    if not url:
        return {"key": key, "url": None, "ok": False, "status_code": None, "latency_ms": None, "error": "unknown_endpoint"}
    t0 = time.perf_counter()
    try:
        client = await get_http_client()
        r = await client.get(url, timeout=timeout_s)
        lat = (time.perf_counter() - t0) * 1000.0
        ok = 200 <= r.status_code < 300
        detail = None
        try:
            if "application/json" in (r.headers.get("content-type") or ""):
                detail = r.json()
        except Exception:
            detail = None
        return {"key": key, "url": url, "ok": ok, "status_code": r.status_code, "latency_ms": round(lat,1), "detail": detail}
    except Exception as e:
        lat = (time.perf_counter() - t0) * 1000.0
        return {"key": key, "url": url, "ok": False, "status_code": None, "latency_ms": round(lat,1), "error": str(e)}

def _runner(required: Iterable[CheckKey], optional: Iterable[CheckKey] = ()):
    req = list(required); opt = list(optional)
    async def _run():
        req_results, opt_results = await asyncio.gather(
            asyncio.gather(*[_probe(k) for k in req]),
            asyncio.gather(*[_probe(k) for k in opt]),
        )
        return list(req_results), list(opt_results)
    return _run

_PS_START = time.time()
def _uptime_s() -> int:
    return int(time.time() - _PS_START)

def build_status_router(*, service: str, version: str | None = None,
                        required_keys: Iterable[CheckKey], optional_keys: Iterable[CheckKey] = ()):
    # ✅ KEEP THE PREFIX; do NOT overwrite router below
    router = APIRouter(prefix=f"/{service}", tags=[f"{service}-status"])
    version = version or os.getenv("ECODIAOS_VERSION", "dev")
    runner = _runner(required_keys, optional_keys)

    @router.get("/healthz")
    async def healthz():
        return {"service": service, "status": "ok", "version": version}

    @router.get("/readyz")
    async def readyz():
        req, _ = await runner()
        ready = all(r.get("ok") for r in req)
        return Response(content=('OK' if ready else 'NOT_READY'),
                        media_type="text/plain", status_code=(200 if ready else 503))

    @router.get("/status")
    async def status():
        req, opt = await runner()
        status = "ok" if all(r.get("ok") for r in req) else "down"
        if status == "ok" and any(not r.get("ok") for r in opt):
            status = "degraded"
        return {
            "service": service,
            "status": status,
            "version": version,
            "uptime_s": _uptime_s(),
            "checks": {"required": req, "optional": opt},
        }

    return router

def router_for(service: str) -> APIRouter:
    cfg = SERVICE_CHECKS[service]
    return build_status_router(service=service,
                               required_keys=cfg.get("required", []),
                               optional_keys=cfg.get("optional", []))

# Back-compat aliases if other modules used old names
build_status_health_router = build_status_router
health_router_for = router_for
