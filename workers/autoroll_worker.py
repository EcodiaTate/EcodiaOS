# scripts/cron/autoroll_worker.py
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client

log = logging.getLogger("autoroll_worker")
logging.basicConfig(level=os.getenv("AUTOROLL_LOGLEVEL", "INFO"))

INTERVAL_SEC = int(os.getenv("AUTOROLL_INTERVAL_SEC", "420"))  # ~7 minutes
MIN_WINDOW = int(os.getenv("AUTOROLL_MIN_WINDOW", "50"))
MAX_P95_MS = int(os.getenv("AUTOROLL_MAX_P95_MS", "1200"))
MIN_UPLIFT = float(os.getenv("AUTOROLL_MIN_UPLIFT", "0.02"))


async def _promote(driver_name: str, incumbent: str | None) -> dict[str, Any]:
    http = await get_http_client()
    r = await http.post(
        ENDPOINTS.AXON_AUTOROLL_PROMOTE_IF_READY
        if hasattr(ENDPOINTS, "AXON_AUTOROLL_PROMOTE_IF_READY")
        else "/autoroll/promote_if_ready",
        json={
            "driver_name": driver_name,
            "incumbent_driver": incumbent,
            "max_p95_ms": MAX_P95_MS,
            "min_uplift": MIN_UPLIFT,
            "min_window": MIN_WINDOW,
        },
    )
    r.raise_for_status()
    return r.json()


async def _list_scorecards() -> list[dict[str, Any]]:
    http = await get_http_client()
    r = await http.get(
        ENDPOINTS.AXON_PROBECRAFT_SCORECARDS
        if hasattr(ENDPOINTS, "AXON_PROBECRAFT_SCORECARDS")
        else "/probecraft/scorecards",
    )
    r.raise_for_status()
    return r.json()


async def main() -> None:
    while True:
        try:
            sc = await _list_scorecards()
            # Try promoting any testing/shadow drivers with healthy windows
            for row in sc:
                name = row.get("driver_name")
                incumbent = row.get("incumbent_driver")
                window = int(row.get("window_size", 0))
                if window < MIN_WINDOW:
                    continue
                res = await _promote(name, incumbent)
                log.info("PromoteTry name=%s res=%s", name, res)
        except Exception as e:
            log.exception("Autoroll tick failed: %s", e)

        await asyncio.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(main())
