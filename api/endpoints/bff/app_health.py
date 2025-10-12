# api/endpoints/bff/app_health.py
from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Response

from core.utils.net_api import get_http_client

router = APIRouter(prefix="/bff/app", tags=["bff-app-health"])

PREF_ORDER = [r"/status$", r"/readyz$", r"/healthz$"]
DANGEROUS = re.compile(r"(delete|reset|shutdown|drop|remove|truncate|wipe|kill)", re.I)
IGNORED = {"", "meta", "openapi.json", "docs", "redoc", "bff", "static", "favicon.ico"}


async def _get_json(path: str, timeout=1.8):
    client = await get_http_client()
    t0 = time.perf_counter()
    r = await client.get(path, timeout=timeout)
    lat = (time.perf_counter() - t0) * 1000.0
    data = None
    if "application/json" in (r.headers.get("content-type") or ""):
        try:
            data = r.json()
        except Exception:
            data = None
    return r.status_code, (data if isinstance(data, dict) else None), lat


def _score(p: str) -> int:
    for i, pat in enumerate(PREF_ORDER):
        if re.search(pat, p):
            return 100 - i
    return 10


def _candidates(entries: list[dict[str, Any]]) -> list[str]:
    flagged = [e["path"] for e in entries if e.get("safe_probe") and "GET" in e.get("methods", [])]
    if flagged:
        return flagged
    c = [
        e["path"]
        for e in entries
        if "GET" in e.get("methods", [])
        and not e.get("has_path_params")
        and not DANGEROUS.search(e["path"])
    ]
    c.sort(key=_score, reverse=True)
    return c[:3]


async def _manifest():
    code, data, _ = await _get_json("/meta/endpoints")
    systems = (data or {}).get("systems", {}) if code == 200 else {}
    norm = {}
    for name, entries in systems.items():
        norm[name] = [
            {
                "path": e.get("path"),
                "methods": e.get("methods", []),
                "has_path_params": bool(e.get("has_path_params")),
                "safe_probe": bool(e.get("safe_probe")),
            }
            for e in entries
            if isinstance(e, dict) and e.get("path")
        ]
    return norm


async def _probe(name: str, entries: list[dict[str, Any]]):
    for p in _candidates(entries):
        try:
            code, data, lat = await _get_json(p)
            if 200 <= code < 300:
                status = (data or {}).get("status") or ("ok" if code == 200 else "down")
                return {
                    "name": name,
                    "ok": status in ("ok", "degraded"),
                    "status": status,
                    "via": p,
                    "latency_ms": round(lat, 1),
                }
        except Exception:
            continue
    return {"name": name, "ok": False, "status": "down", "via": None}


async def _aggregate(required: list[str] | None = None):
    mf = await _manifest()
    names = [n for n in mf.keys() if n not in IGNORED]
    if required:
        req = set(required)
        names = [n for n in names if n in req]
    results = await asyncio.gather(*[_probe(n, mf[n]) for n in names])
    overall = "ok"
    if any(r["status"] == "down" for r in results):
        overall = "down"
    elif any((r["status"] == "degraded") or (not r["ok"]) for r in results):
        overall = "degraded"
    return {"overall": overall, "systems": results, "ts": int(time.time())}


@router.get("/healthz")
async def app_healthz():
    return {"service": "app", "status": "ok", "version": os.getenv("ECODIAOS_VERSION", "dev")}


@router.get("/status")
async def app_status():
    return await _aggregate()


@router.get("/readyz")
async def app_readyz():
    required = [s.strip() for s in os.getenv("APP_HEALTH_REQUIRE", "").split(",") if s.strip()]
    agg = await _aggregate(required or None)
    ready = agg["overall"] == "ok" and all(r["ok"] for r in agg["systems"])
    return Response(
        content=("OK" if ready else "NOT_READY"),
        media_type="text/plain",
        status_code=(200 if ready else 503),
    )
