# debug/log_middleware.py
from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

MAX_BYTES = 32_000


class LogBodiesOnError(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        body = await request.body()
        body_snip = body[:MAX_BYTES]
        try:
            resp = await call_next(request)
        except Exception as e:
            print(
                f"[REQ-ERR] {request.method} {request.url} body={body_snip!r} -> EXC={e!r}",
                flush=True,
            )
            raise
        if resp.status_code >= 500:
            # Safely read resp body (may be streaming; we re-wrap)
            raw = b""
            if hasattr(resp, "body_iterator"):
                async for chunk in resp.body_iterator:
                    raw += chunk
                resp = Response(
                    content=raw,
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    media_type=getattr(resp, "media_type", None),
                )
            print(
                f"[REQ-500] {request.method} {request.url} body={body_snip!r} -> RESP={raw[:MAX_BYTES]!r}",
                flush=True,
            )
        return resp
