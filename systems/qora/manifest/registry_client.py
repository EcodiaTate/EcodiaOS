# qora/systems/manifest/registry_client.py

from __future__ import annotations
from typing import Any

# --- BEFORE ---
# from core.utils.net_api_registry import LIVE_ENDPOINTS

# --- AFTER ---
from core.utils.net_api import LIVE_ENDPOINTS


async def get_endpoint_aliases() -> dict[str, str]:
    # This will now correctly call the main, initialized registry
    await LIVE_ENDPOINTS.refresh()
    return LIVE_ENDPOINTS.snapshot_aliases()


async def get_endpoint_routes() -> dict[str, dict[str, Any]]:
    await LIVE_ENDPOINTS.refresh()
    return LIVE_ENDPOINTS.snapshot_routes()
