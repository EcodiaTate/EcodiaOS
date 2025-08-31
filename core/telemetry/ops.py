from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from core.telemetry.context import current
from core.telemetry.harvest import (
    harvest_common,
    harvest_llm_headers,
    harvest_nova_headers,
    merge_metrics,
)


async def request_and_harvest(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json: Any = None,
    headers: Mapping[str, str] | None = None,
    harvest: bool = True,
    **kw: Any,
) -> httpx.Response:
    """Make an HTTP call and, if enabled, harvest standard metrics headers into the current TelemetryContext."""
    resp = await client.request(method.upper(), url, json=json, headers=headers, **kw)
    if harvest:
        h = resp.headers
        blob = merge_metrics(
            harvest_common(h),
            harvest_llm_headers(h),
            harvest_nova_headers(h),
        )
        current().add(blob)
    return resp


async def post_json_and_harvest(
    client: httpx.AsyncClient,
    url: str,
    *,
    json: Any,
    headers: Mapping[str, str] | None = None,
    harvest: bool = True,
    **kw: Any,
) -> httpx.Response:
    return await request_and_harvest(
        client,
        "POST",
        url,
        json=json,
        headers=headers,
        harvest=harvest,
        **kw,
    )
