from __future__ import annotations

import json
import os
import time
from collections import OrderedDict
from typing import Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class _TTLGate:
    def __init__(self, ttl_sec: float, max_keys: int = 1024):
        self.ttl = float(ttl_sec)
        self.max = int(max_keys)
        self._last: OrderedDict[str, float] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        last = self._last.get(key)
        if last is not None and (now - last) < self.ttl:
            return False
        if key in self._last:
            self._last.move_to_end(key, last=True)
        self._last[key] = now
        while len(self._last) > self.max:
            self._last.popitem(last=False)
        return True


_HINT_TTL = float(os.getenv("SYNAPSE_HINT_TTL_SEC", "0.5"))
_CAPS_TTL = float(os.getenv("AXON_CAPS_TTL_SEC", "2.0"))

_HINT_GATE = _TTLGate(_HINT_TTL)
_CAPS_GATE = _TTLGate(_CAPS_TTL)

# simple coalescing cache for /axon/mesh/capabilities
_caps_cache: tuple[float, bytes, str] | None = None  # (ts, body_bytes, media_type)


def _rebuild_request_with_body(request: Request, body: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive=receive)


class TTLMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Gate POST /synapse/hint
        if path == "/synapse/hint" and request.method == "POST":
            body_bytes = await request.body()  # read once
            ns = ""
            key = ""
            try:
                data = json.loads(body_bytes.decode("utf-8") or "{}")
                ns = str(data.get("namespace") or request.query_params.get("namespace") or "")
                key = str(data.get("key") or request.query_params.get("key") or "")
            except Exception:
                # keep defaults; still dedupe empties together
                pass

            if not _HINT_GATE.allow(f"{ns}:{key}"):
                return JSONResponse(
                    {"ok": True, "rate_limited": True, "ns": ns, "key": key},
                    status_code=200,
                    headers={"X-TTL-Gate": "synapse-hint:dedup"},
                )

            # rebuild request so downstream handler still sees the body
            req2 = _rebuild_request_with_body(request, body_bytes)
            resp = await call_next(req2)
            resp.headers.setdefault("X-TTL-Gate", "synapse-hint:pass")
            return resp

        # Gate/Coalesce GET /axon/mesh/capabilities
        if path == "/axon/mesh/capabilities" and request.method == "GET":
            global _caps_cache
            if not _CAPS_GATE.allow("caps") and _caps_cache is not None:
                _, cached_bytes, media_type = _caps_cache
                return Response(
                    cached_bytes,
                    media_type=media_type,
                    status_code=200,
                    headers={"X-TTL-Gate": "axon-caps:cached"},
                )

            # allow through; capture response for short-term cache
            resp = await call_next(request)
            try:
                body_bytes = b"".join([chunk async for chunk in resp.body_iterator])  # drain
                media = resp.media_type or "application/json"
                _caps_cache = (time.monotonic(), body_bytes, media)
                # rebuild response since we consumed iterator
                new_resp = Response(
                    content=body_bytes,
                    media_type=media,
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                )
                new_resp.headers.setdefault("X-TTL-Gate", "axon-caps:pass")
                return new_resp
            except Exception:
                resp.headers.setdefault("X-TTL-Gate", "axon-caps:pass")
                return resp

        # Everything else
        return await call_next(request)
