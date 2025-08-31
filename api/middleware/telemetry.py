# file: api/middleware/telemetry.py
from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

DECISION_HEADER = "x-decision-id"
BUDGET_HEADER = "x-budget-ms"
DEADLINE_HEADER = "x-deadline-ts"


def _stamp_cost(res: Response, start: float) -> None:
    try:
        res.headers["X-Cost-MS"] = str(int((time.perf_counter() - start) * 1000))
    except Exception:
        pass


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def _telemetry_mw(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        t0 = time.perf_counter()
        # Propagate / normalise headers
        decision_id = request.headers.get(DECISION_HEADER) or f"dec_{uuid.uuid4().hex[:10]}"
        budget_ms = request.headers.get(BUDGET_HEADER)
        deadline_ts = request.headers.get(DEADLINE_HEADER)

        response: Response
        try:
            response = await call_next(request)
        finally:
            pass

        # Echo for tracing joins
        response.headers["X-Decision-Id"] = decision_id
        if budget_ms is not None and BUDGET_HEADER not in response.headers:
            response.headers["X-Budget-MS"] = budget_ms
        if deadline_ts is not None and DEADLINE_HEADER not in response.headers:
            response.headers["X-Deadline-TS"] = deadline_ts

        _stamp_cost(response, t0)
        return response
