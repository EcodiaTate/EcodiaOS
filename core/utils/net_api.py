# core/utils/net_api.py
from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Mapping
from typing import Any, Dict, Optional

import httpx

# =============================================================================
# Config
# =============================================================================
BASE_URL = os.getenv("ECODIAOS_BASE_URL", "http://localhost:8000").rstrip("/")
DEFAULT_HTTP_TIMEOUT = float(os.getenv("ECODIAOS_HTTP_TIMEOUT", "60.0"))
QORA_API_KEY = os.getenv("QORA_API_KEY", "dev")

META_URL = os.getenv("QORA_META_ENDPOINT_URL", "/meta/endpoints")
META_TTL_SEC = int(os.getenv("QORA_META_TTL_SEC", "30"))

DEFAULT_INTERNAL_HEADERS = {"x-ecodia-immune": "1"}


# =============================================================================
# Live Endpoint Registry
# =============================================================================
class LiveEndpointRegistry:
    """
    Pulls live aliases/schemas from /meta/endpoints with ETag + TTL caching.
    This is the new source of truth for endpoint paths.
    """

    def __init__(self, base_url: str, meta_url: str, ttl_sec: int):
        self._base_url = base_url
        self._meta_url = meta_url
        self._ttl = ttl_sec
        self._aliases: dict[str, str] = {}
        self._synonyms: dict[str, str] = {}
        self._etag: str | None = None
        self._ts: float = 0.0
        self._lock = asyncio.Lock()

    async def refresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._ts) < self._ttl and self._aliases:
            return

        async with self._lock:
            if not force and (now - self._ts) < self._ttl and self._aliases:
                return

            headers = {"x-ecodia-immune": "1"}
            if self._etag:
                headers["If-None-Match"] = self._etag

            # highlight-start
            # ADDED A RETRY LOOP TO FIX THE STARTUP RACE CONDITION
            last_exception = None
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(base_url=self._base_url, timeout=5.0) as client:
                        resp = await client.get(self._meta_url, headers=headers)

                    if resp.status_code == 304:
                        self._ts = now
                        return

                    resp.raise_for_status()
                    data = resp.json()

                    aliases, _, synonyms = self._normalize(data)

                    self._aliases = aliases
                    self._synonyms = synonyms
                    self._etag = resp.headers.get("ETag")
                    self._ts = now
                    print(
                        f"[net_api] Refreshed Endpoints overlay: {len(self._aliases)} aliases found."
                    )
                    return  # Success, exit the retry loop

                except Exception as e:
                    last_exception = e
                    if attempt < 2:
                        await asyncio.sleep(1)  # Wait and retry

            # If all retries fail, log the final error
            self._ts = now
            print(
                f"[net_api] WARNING: Could not refresh endpoint registry after multiple attempts. Using stale data. Error: {last_exception}"
            )
            # highlight-end

    def populate_from_app_routes(self, routes: Any):
        """
        Directly populates the registry from the app's route objects,
        bypassing the unreliable self-HTTP call during startup.
        """
        aliases: dict[str, str] = {}
        for route in routes:
            if not hasattr(route, "path"):
                continue

            # Use the existing logic from the class to create a consistent alias
            alias = self._alias_from_path(route.path)
            aliases[alias] = route.path

        self._aliases = aliases
        self._ts = time.time()  # Mark the cache as fresh
        print(f"✅ [net_api] Registry populated with {len(self._aliases)} aliases.")

    def path(self, alias: str) -> str:
        key = alias.upper()
        key = self._synonyms.get(key, key)
        path = self._aliases.get(key)
        if path is None:
            raise AttributeError(f"[unknown_endpoint] No endpoint registered for alias '{alias}'.")
        return path

    def snapshot_aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    def _normalize(self, data: Any) -> tuple[dict[str, str], dict[str, Any], dict[str, str]]:
        if isinstance(data, dict) and "aliases" in data:
            aliases = {k.upper(): v for k, v in data.get("aliases", {}).items()}
            routes = {r.get("alias", "").upper(): r for r in data.get("routes", [])}
            synonyms = {k.upper(): v.upper() for k, v in data.get("synonyms", {}).items()}
            return aliases, routes, synonyms

        if isinstance(data, dict) and "paths" in data:
            aliases = {self._alias_from_path(p): p for p in data["paths"]}
            return aliases, {}, {}

        return {}, {}, {}

    @staticmethod
    def _alias_from_path(path: str) -> str:
        if not path:
            return "UNKNOWN"
        return path.strip("/").upper().replace("/", "_").replace("-", "_")


LIVE_ENDPOINTS = LiveEndpointRegistry(base_url=BASE_URL, meta_url=META_URL, ttl_sec=META_TTL_SEC)


# =============================================================================
# Public Interface
# =============================================================================
class _EndpointsProxy:
    def __getattr__(self, name: str) -> str:
        return LIVE_ENDPOINTS.path(name)


ENDPOINTS = _EndpointsProxy()


async def init_net_api():
    await get_http_client()
    await LIVE_ENDPOINTS.refresh(force=True)


_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(base_url=BASE_URL, timeout=DEFAULT_HTTP_TIMEOUT)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def _ensure_mapping(name: str, obj: Mapping[str, Any] | None) -> dict[str, Any]:
    if obj is None:
        return {}
    if not isinstance(obj, Mapping):
        raise TypeError(f"{name} must be a Mapping, got {type(obj).__name__}")
    return dict(obj)


def _normalize_path(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return path if path.startswith("/") else f"/{path}"


def _with_internal_defaults(h: Mapping[str, Any] | None) -> dict[str, Any]:
    out = _ensure_mapping("headers", h)
    for k, v in DEFAULT_INTERNAL_HEADERS.items():
        out.setdefault(k, v)
    return out


async def _request(
    method: str,
    path: str,
    *,
    json: Any = None,
    headers: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    timeout: float | None = None,
    **kw: Any,
) -> httpx.Response:
    client = await get_http_client()
    hdrs = _ensure_mapping("headers", headers)
    prms = _ensure_mapping("params", params)
    req_timeout = httpx.Timeout(timeout if timeout is not None else DEFAULT_HTTP_TIMEOUT)
    return await client.request(
        method.upper(),
        _normalize_path(path),
        json=json,
        headers=hdrs,
        params=prms,
        timeout=req_timeout,
        **kw,
    )


async def post(path: str, **kwargs):
    return await _request("POST", path, **kwargs)


async def post_internal(path: str, **kwargs):
    headers = kwargs.pop("headers", {})
    return await _request("POST", path, headers=_with_internal_defaults(headers), **kwargs)
