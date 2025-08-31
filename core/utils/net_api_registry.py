# core/net_api/registry.py
from __future__ import annotations

"""
Live endpoint registry (overlay) with ETag/TTL caching + synonym support.

Pulls aliases and optional route schemas from `/meta/endpoints` and exposes:
    - snapshot_aliases() -> {ALIAS: "/path"}
    - snapshot_routes()  -> {ALIAS: {alias, path, method, system?, req_schema?, res_schema?}}
    - path(alias)        -> "/path" (resolves synonyms, uppercases)
    - route(alias)       -> route dict (resolves synonyms)

Input payloads tolerated (server-controlled):
    A) {"aliases": {"AXON_ACT": "/axon/act", ...},
        "routes":  [{"alias": "...", "path": "...", "method": "POST", "req_schema": {...}, "res_schema": {...}, "system": "..."}],
        "synonyms": {"SIMULA_CODEGEN": "SIMULA_JOBS_CODEGEN", ...}  # optional
       }

    B) {"paths": {"/simula/jobs/codegen": {...}, ...}}              # OpenAPI-ish; we derive aliases from paths

    C) [{"alias": "...", "path": "...", "method": "POST", ...}, ...]# flat list of routes

Env knobs:
    ECODIAOS_BASE_URL            (default "http://localhost:8000")
    QORA_META_ENDPOINT_URL       (default "/meta/endpoints")
    QORA_META_TTL_SEC            (default "30")
    QORA_META_SYNONYMS_JSON      (optional JSON mapping of alias->canonical, merged with server synonyms)
    QORA_META_ENABLE_FUZZY_CANON (default "1") normalize alias-from-path more aggressively
"""

import asyncio
import json
import os
import time
from typing import Any

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

# ------------------------------- ENV -------------------------------

_META_URL = os.getenv("QORA_META_ENDPOINT_URL", "/meta/endpoints")
_TTL_SEC = int(os.getenv("QORA_META_TTL_SEC", "30"))
_BASE_URL = os.getenv("ECODIAOS_BASE_URL", "http://localhost:8000")
_FUZZY_CANON = os.getenv("QORA_META_ENABLE_FUZZY_CANON", "1") == "1"

# Optional client-side synonyms (merged with server-provided)
try:
    _CLIENT_SYNONYMS: dict[str, str] = {
        k.upper(): v.upper()
        for k, v in json.loads(os.getenv("QORA_META_SYNONYMS_JSON", "{}")).items()
    }
except Exception:
    _CLIENT_SYNONYMS = {}


# Some sane defaults you can remove later once all call-sites are canonical
_DEFAULT_SYNONYMS: dict[str, str] = {
}


# --------------------------- Registry ----------------------------


class LiveEndpointRegistry:
    """
    Pulls live aliases/schemas from /meta/endpoints with ETag + TTL caching.
    """

    def __init__(
        self,
        base_url: str | None = None,
        meta_url: str | None = None,
        ttl_sec: int = _TTL_SEC,
    ):
        self._base = (base_url or _BASE_URL).rstrip("/")
        self._meta = meta_url or _META_URL
        self._ttl = ttl_sec

        self._aliases: dict[str, str] = {}
        self._routes: dict[str, dict[str, Any]] = {}  # key = alias (UPPER)
        self._synonyms: dict[str, str] = {}  # alias -> canonical alias (both UPPER)

        self._etag: str | None = None
        self._ts: float = 0.0
        self._lock = asyncio.Lock()

    # ---------------- Public API ----------------

    async def refresh(self, force: bool = False) -> None:
        """
        Populate/refresh the cache if TTL expired or forced.
        Uses ETag for conditional GET; falls back to last-good data on errors.
        """
        if httpx is None:
            return

        now = time.time()
        if not force and (now - self._ts) < self._ttl and self._aliases:
            return

        async with self._lock:
            if not force and (now - self._ts) < self._ttl and self._aliases:
                return

            headers = {}
            if self._etag:
                headers["If-None-Match"] = self._etag

            try:
                async with httpx.AsyncClient(base_url=self._base, timeout=15.0) as client:
                    resp = await client.get(self._meta, headers={**headers, "x-ecodia-immune": "1"})

                if resp.status_code == 304:
                    self._ts = now
                    return
                resp.raise_for_status()
                data = resp.json()

                aliases, routes, synonyms = self._normalize(data)
                # Merge in default + client-provided synonyms
                synonyms = {
                    **_DEFAULT_SYNONYMS,
                    **synonyms,
                    **_CLIENT_SYNONYMS,
                }

                # Apply synonyms (alias -> canonical) to produce a fully-resolved view
                aliases, routes = self._apply_synonyms(aliases, routes, synonyms)

                # Commit atomically
                self._aliases = aliases
                self._routes = routes
                self._synonyms = synonyms
                self._etag = resp.headers.get("ETag") or self._etag
                self._ts = now
            except Exception:
                # Swallow fetch errors; keep last-good snapshot
                # You may want to log here via your logging facility
                self._ts = now  # still bump ts slightly to avoid hot loop

    def snapshot_aliases(self) -> dict[str, str]:
        """Shallow copy of alias -> path, including synonyms."""
        return dict(self._aliases)

    def snapshot_routes(self) -> dict[str, dict[str, Any]]:
        """Shallow copy of alias -> route dict, including synonyms."""
        return {k: dict(v) for k, v in self._routes.items()}

    def path(self, alias: str) -> str:
        """Return path for alias (resolves synonyms); raises KeyError if unknown."""
        key = self._resolve_alias(alias)
        if key not in self._aliases:
            raise KeyError(f"Unknown endpoint alias: {alias}")
        return self._aliases[key]

    def route(self, alias: str) -> dict[str, Any]:
        """Return route dict for alias (resolves synonyms). Empty dict if unknown."""
        key = self._resolve_alias(alias)
        return dict(self._routes.get(key, {}))

    def exists(self, alias: str) -> bool:
        key = self._resolve_alias(alias, strict=False)
        return key in self._aliases

    def synonyms(self) -> dict[str, str]:
        """A snapshot of current synonyms map (alias -> canonical)."""
        return dict(self._synonyms)

    # ---------------- Internals ----------------

    def _resolve_alias(self, alias: str, strict: bool = True) -> str:
        up = (alias or "").upper()
        canon = self._synonyms.get(up, up)
        if strict:
            return canon
        # If the raw alias exists but canon does not, prefer raw
        return canon if canon in self._aliases else up

    def _normalize(
        self,
        data: Any,
    ) -> tuple[dict[str, str], dict[str, dict[str, Any]], dict[str, str]]:
        """
        Return (aliases, routes, synonyms) all keyed by UPPER alias.
        """
        aliases: dict[str, str] = {}
        routes: dict[str, dict[str, Any]] = {}
        synonyms: dict[str, str] = {}

        # Case A: {"aliases": {...}, "routes":[...], "synonyms": {...}}
        if isinstance(data, dict) and "aliases" in data:
            for k, v in (data.get("aliases") or {}).items():
                aliases[k.upper()] = str(v)

            if isinstance(data.get("synonyms"), dict):
                for a, c in data["synonyms"].items():
                    synonyms[a.upper()] = c.upper()

            for r in data.get("routes") or []:
                alias = (r.get("alias") or self._alias_from_path(r.get("path", ""))).upper()
                routes[alias] = {
                    "alias": alias,
                    "path": r.get("path"),
                    "method": (r.get("method") or "POST").upper(),
                    "system": r.get("system"),
                    "req_schema": r.get("req_schema"),
                    "res_schema": r.get("res_schema"),
                }
            # Backfill missing routes from aliases
            for a, p in aliases.items():
                routes.setdefault(a, {"alias": a, "path": p, "method": "POST"})
            return aliases, routes, synonyms

        # Case B: OpenAPI-ish {"paths": {...}}
        if isinstance(data, dict) and "paths" in data:
            for p in list((data.get("paths") or {}).keys()):
                a = self._alias_from_path(p)
                aliases[a] = p
                routes[a] = {"alias": a, "path": p, "method": "POST"}
            return aliases, routes, synonyms

        # Case C: list of route objects
        if isinstance(data, list):
            for r in data:
                alias = (r.get("alias") or self._alias_from_path(r.get("path", ""))).upper()
                path = r.get("path")
                method = (r.get("method") or "POST").upper()
                aliases[alias] = path
                routes[alias] = {
                    "alias": alias,
                    "path": path,
                    "method": method,
                    "req_schema": r.get("req_schema"),
                    "res_schema": r.get("res_schema"),
                    "system": r.get("system"),
                }
            return aliases, routes, synonyms

        # Unknown shape → empty
        return {}, {}, {}

    def _apply_synonyms(
        self,
        aliases: dict[str, str],
        routes: dict[str, dict[str, Any]],
        synonyms: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        """
        Materialize synonyms so callers can query either alias or canonical.
        """
        if not synonyms:
            return aliases, routes

        merged_aliases = dict(aliases)
        merged_routes = dict(routes)

        for syn, canon in synonyms.items():
            c = canon.upper()
            s = syn.upper()
            if c in aliases:
                # alias-to-path
                merged_aliases.setdefault(s, aliases[c])
                # alias-to-route
                if c in routes:
                    merged_routes.setdefault(s, {**routes[c], "alias": s})
            # If the canonical doesn't exist yet, leave the synonym unresolved;
            # callers will still see KeyError for both until server adds the canonical.

        return merged_aliases, merged_routes

    @staticmethod
    def _alias_from_path(path: str) -> str:
        """
        Derive ALIAS from a REST path. Examples:
            "/simula/jobs/codegen"         -> "SIMULA_JOBS_CODEGEN"
            "/qora/arch/execute-by-uid"    -> "QORA_ARCH_EXECUTE_BY_UID"
            "/synapse/core/tasks/base"     -> "SYNAPSE_TASKS_BASE"  (drops 'core')
        """
        if not path:
            return "UNKNOWN"
        parts = [p for p in str(path).strip().split("/") if p]
        # drop generic noise segments that don't carry semantic alias meaning
        noise = {"core"}
        parts = [p for p in parts if p not in noise]
        alias = "_".join(parts).upper()
        if _FUZZY_CANON:
            alias = alias.replace("-", "_")
        return alias or "UNKNOWN"


# Singleton (optional)
LIVE_ENDPOINTS = LiveEndpointRegistry()
