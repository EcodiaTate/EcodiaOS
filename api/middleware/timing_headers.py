from __future__ import annotations

import time

from starlette.types import ASGIApp, Receive, Scope, Send


class TimingHeadersMiddleware:
    """
    Stamps X-Cost-MS on every inbound route, echoes correlation headers,
    and (for /axon/*) also stamps X-Axon-Action-Cost-MS.

    Add via: app.add_middleware(TimingHeadersMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        start = time.perf_counter()
        req_headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                dur_ms = (time.perf_counter() - start) * 1000.0
                headers = [(b"x-cost-ms", f"{dur_ms:.1f}".encode())]
                path = scope.get("path") or ""
                if path.startswith("/axon/"):
                    headers.append((b"x-axon-action-cost-ms", f"{dur_ms:.1f}".encode()))
                # echo known correlation headers if present
                for hk in (
                    "x-decision-id",
                    "x-budget-ms",
                    "x-spec-id",
                    "x-spec-version",
                    "x-arm-id",
                    "x-call-id",
                ):
                    if hk in req_headers:
                        headers.append((hk.encode(), req_headers[hk].encode()))
                message = {**message, "headers": list(message.get("headers", [])) + headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
