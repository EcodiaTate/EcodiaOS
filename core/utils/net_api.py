# core/utils/net_api.py
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, Mapping, Optional

import httpx

# =============================================================================
# Config
# =============================================================================
BASE_URL = os.getenv("ECODIAOS_BASE_URL", "http://localhost:8000").rstrip("/")
DEFAULT_HTTP_TIMEOUT = float(os.getenv("ECODIAOS_HTTP_TIMEOUT", "60.0"))
QORA_API_KEY = os.getenv("QORA_API_KEY", "dev")

# Config for the new LiveEndpointRegistry
META_URL = os.getenv("QORA_META_ENDPOINT_URL", "/meta/endpoints")
META_TTL_SEC = int(os.getenv("QORA_META_TTL_SEC", "30"))

# =============================================================================
# Live Endpoint Registry (The New, Correct Implementation)
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
        self._aliases: Dict[str, str] = {}
        self._synonyms: Dict[str, str] = {}
        self._etag: Optional[str] = None
        self._ts: float = 0.0
        self._lock = asyncio.Lock()

    async def refresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._ts) < self._ttl and self._aliases:
            return

        async with self._lock:
            # Double-check after acquiring lock
            if not force and (now - self._ts) < self._ttl and self._aliases:
                return

            headers = {"x-ecodia-immune": "1"}
            if self._etag:
                headers["If-None-Match"] = self._etag

            try:
                async with httpx.AsyncClient(base_url=self._base_url, timeout=15.0) as client:
                    resp = await client.get(self._meta_url, headers=headers)

                if resp.status_code == 304: # Not Modified
                    self._ts = now
                    return
                
                resp.raise_for_status()
                data = resp.json()

                # Normalize the payload from the server
                aliases, _, synonyms = self._normalize(data)
                
                # Update state atomically
                self._aliases = aliases
                self._synonyms = synonyms
                self._etag = resp.headers.get("ETag")
                self._ts = now
                print(f"[net_api] Refreshed Endpoints overlay: {len(self._aliases)} aliases found.")

            except Exception as e:
                # On failure, keep the last known good data but update timestamp to prevent a hot-loop of failures.
                self._ts = now
                print(f"[net_api] WARNING: Could not refresh endpoint registry. Using stale data. Error: {e}")

    def path(self, alias: str) -> str:
        key = alias.upper()
        # Resolve synonym if one exists
        key = self._synonyms.get(key, key)
        
        path = self._aliases.get(key)
        if path is None:
            raise AttributeError(f"[unknown_endpoint] No endpoint registered for alias '{alias}'.")
        return path

    def _normalize(self, data: Any) -> tuple[Dict[str, str], Dict[str, Any], Dict[str, str]]:
        if isinstance(data, dict) and "aliases" in data: # Format A
            aliases = {k.upper(): v for k, v in data.get("aliases", {}).items()}
            routes = {r.get("alias", "").upper(): r for r in data.get("routes", [])}
            synonyms = {k.upper(): v.upper() for k, v in data.get("synonyms", {}).items()}
            return aliases, routes, synonyms
        
        if isinstance(data, dict) and "paths" in data: # Format B (OpenAPI-ish)
            aliases = {self._alias_from_path(p): p for p in data["paths"]}
            return aliases, {}, {}
            
        return {}, {}, {}

    @staticmethod
    def _alias_from_path(path: str) -> str:
        if not path: return "UNKNOWN"
        # Correctly transform /equor/compose -> EQUOR_COMPOSE
        return path.strip("/").upper().replace("/", "_").replace("-", "_")

# Create the singleton instance
LIVE_ENDPOINTS = LiveEndpointRegistry(base_url=BASE_URL, meta_url=META_URL, ttl_sec=META_TTL_SEC)

# =============================================================================
# Public Interface (ENDPOINTS proxy and init)
# =============================================================================
class _EndpointsProxy:
    """A proxy that provides attribute-style access to the live registry."""
    def __getattr__(self, name: str) -> str:
        # This is now a direct, safe lookup on the new registry
        return LIVE_ENDPOINTS.path(name)

ENDPOINTS = _EndpointsProxy()

async def init_net_api():
    """Explicitly initializes the network layer and endpoint registry."""
    print("[net_api] Initializing network layer and endpoint registry...")
    await get_http_client() # Initializes the client
    await LIVE_ENDPOINTS.refresh(force=True) # Fetches endpoints immediately on startup

# =============================================================================
# HTTP Client and Request Helpers (Preserved for safety and consistency)
# =============================================================================
_http_client: Optional[httpx.AsyncClient] = None

async def get_http_client() -> httpx.AsyncClient:
    """Returns a shared, singleton httpx.AsyncClient."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(base_url=BASE_URL, timeout=DEFAULT_HTTP_TIMEOUT)
    return _http_client

async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None