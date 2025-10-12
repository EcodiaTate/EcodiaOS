# api/endpoints/axon/axon_debug.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, cast

from fastapi import APIRouter, HTTPException, Query

from systems.axon.loop.event_tap import dump as dump_recent
from systems.axon.mesh.sdk import DriverInterface

# Try the registry first; fall back to a local instance
try:
    from systems.axon.dependencies import get_driver_registry
except Exception:
    get_driver_registry = None  # type: ignore[assignment]

# Import the concrete driver if available; it may fail at import time in some envs
try:
    from systems.axon.drivers.rss_driver import RssDriver  # type: ignore[unused-ignore]
except Exception:
    RssDriver = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    # Only for type-checkers; doesn't run at runtime
    from systems.axon.drivers.rss_driver import RssDriver as _RssDriver  # noqa: F401

rss_debug_router = APIRouter(tags=["axon:debug"])


def _get_rss_driver() -> DriverInterface:
    """
    Returns the shared registry instance if available; otherwise
    constructs a local driver (debug-only).
    """
    if get_driver_registry:
        try:
            reg = get_driver_registry()
            if hasattr(reg, "get"):
                d = reg.get("rss")
                if d:
                    # We expect this to conform to DriverInterface
                    return cast(DriverInterface, d)
        except Exception:
            # fall through to local
            pass

    if RssDriver is not None:
        return cast(DriverInterface, RssDriver())  # local instance (bypasses scheduler caches)

    raise HTTPException(500, "RSS driver unavailable")


@rss_debug_router.get("/pull")
async def one_off_pull(
    url: str | None = Query(None),
    max_items: int = Query(3, ge=1, le=50),
    timeout: float = Query(5.0, gt=0),
) -> list[dict[str, Any]]:
    """
    Directly invoke the RSS driver (bypassing scheduler) and return canonicalized events.
    Use this to prove parsing + canonicalization end-to-end.
    """
    drv = _get_rss_driver()
    params: dict[str, Any] = {"max_items": max_items, "timeout": timeout}
    if url:
        params["url"] = url

    out: list[dict[str, Any]] = []
    async for ev in drv.pull(params):  # type: ignore[attr-defined]
        md = getattr(ev, "model_dump", None)
        out.append(md() if callable(md) else getattr(ev, "__dict__", {"repr": repr(ev)}))
        if len(out) >= max_items:
            break
    return out


@rss_debug_router.get("/recent")
async def recent_ingested(limit: int = Query(20, ge=1, le=200)):
    """
    Mirror what the scheduler actually saw (via the tap). If this is empty
    while /axon/debug/pull returns events, your scheduler wiring is the gap.
    """
    return dump_recent(limit=limit)


@rss_debug_router.get("/rss/state")
async def rss_state():
    """
    Inspect driver-internal dedupe caches to understand 'yielded=0' situations.
    If you got the shared instance, these numbers reflect the scheduler's view.
    """
    drv = _get_rss_driver()
    state = {
        "seen_size": len(getattr(drv, "_seen", {})),
        "seen_sample": list(getattr(drv, "_seen", {}).keys())[:5],
        "pull_cache_keys": list(getattr(drv, "_pull_cache", {}).keys())[:3],
        "id_map_keys": list(getattr(drv, "_id_map", {}).keys())[:5],
        "last_pull_id_by_feed": dict(getattr(drv, "_last_pull_id_by_feed", {})),
        "started_at": getattr(drv, "_started_at", None),
        "first_pull": getattr(drv, "_first_pull", None),
    }
    return state


@rss_debug_router.post("/rss/reset_seen")
async def rss_reset_seen():
    """
    Clear dedupe so the next scheduler pull can emit again.
    This operates on the *shared* driver when available.
    """
    drv = _get_rss_driver()
    cleared: dict[str, int] = {}

    seen = getattr(drv, "_seen", None)
    if isinstance(seen, dict):
        cleared["seen_before"] = len(seen)
        seen.clear()

    id_map = getattr(drv, "_id_map", None)
    if isinstance(id_map, dict):
        cleared["id_map_before"] = len(id_map)
        id_map.clear()

    last_pull = getattr(drv, "_last_pull_id_by_feed", None)
    if isinstance(last_pull, dict):
        cleared["last_pull_before"] = len(last_pull)
        last_pull.clear()

    # Do not clear _pull_cache (used for /rss/repro)
    return {"ok": True, **cleared}


@rss_debug_router.get("/rss/repro/{guid:path}")
async def rss_repro(guid: str):
    drv = _get_rss_driver()
    try:
        cap = await drv.repro_bundle(id=guid, kind="event")
    except KeyError:
        raise HTTPException(404, f"No cached feed content for GUID {guid}")
    md = getattr(cap, "model_dump", None)
    return md() if callable(md) else getattr(cap, "__dict__", {"repr": repr(cap)})
