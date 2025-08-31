from __future__ import annotations

from typing import Any

from core.utils.net_api_registry import LIVE_ENDPOINTS


async def get_endpoint_aliases() -> dict[str, str]:
    await LIVE_ENDPOINTS.refresh()
    return LIVE_ENDPOINTS.snapshot_aliases()


async def get_endpoint_routes() -> dict[str, dict[str, Any]]:
    await LIVE_ENDPOINTS.refresh()
    return LIVE_ENDPOINTS.snapshot_routes()
