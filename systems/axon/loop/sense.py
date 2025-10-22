# systems/axon/loop/sense.py
from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, Iterable
from typing import Optional

from core.llm.bus import event_bus
from systems.axon.loop import event_tap  # may expose .tap() or something else
from systems.axon.mesh.sdk import DriverInterface

# -----------------------------------------------------------------------------
# Optional: Driver Registry (existing in your repo)
# -----------------------------------------------------------------------------
try:
    from systems.axon.dependencies import get_driver_registry
except Exception:
    get_driver_registry = None  # type: ignore[assignment]

# -----------------------------------------------------------------------------
# Optional: Source Registry Ingestor (new registry-based ingestion path)
# -----------------------------------------------------------------------------
try:
    from systems.axon.registry.feeds import SourceRegistryIngestor  # provided in registry/feeds.py
except Exception:
    SourceRegistryIngestor = None  # type: ignore[assignment]

AXON_DEBUG = os.getenv("AXON_DEBUG", "0") == "1"
PUBLISH_EVENTS = (
    os.getenv("AXON_PUBLISH_EVENTS", "1") == "1"
)  # allow turning off bus publish for tests

# Registry env toggles/paths
USE_REGISTRY = os.getenv("AXON_USE_REGISTRY", "1") == "1"
REG_PATH_MAIN = os.getenv("AXON_FEEDS_MAIN", "config/feeds.yml")
REG_PATH_LOCAL = os.getenv("AXON_FEEDS_LOCAL", "config/feeds.local.yml")

# Safety guards to avoid unbounded loops when a source is extremely chatty
MAX_EVENTS_PER_TICK = int(
    os.getenv("AXON_SENSE_MAX_EVENTS", "1000"),
)  # hard cap per tick (drivers + registry)
MAX_REGISTRY_EVENTS_PER_TICK = int(
    os.getenv("AXON_REGISTRY_MAX_PER_TICK", "500"),
)  # sub-cap for registry path
MAX_DRIVER_EVENTS_PER_DRIVER = int(os.getenv("AXON_DRIVER_MAX_PER_PULL", "500"))  # per-driver cap


# -----------------------------------------------------------------------------
# Resilient TAP helper (supports event_tap.record OR event_tap.tap; else no-op)
# -----------------------------------------------------------------------------
_TAP_FIRST_FAILURE_LOGGED = False


def _emit_to_tap(ev) -> None:
    """
    Send event to the debug tap if available. Supports:
      - event_tap.record(ev)
      - event_tap.tap(ev)
      - no-op if neither exists
    Emits a single warning per run if no supported function exists.
    """
    global _TAP_FIRST_FAILURE_LOGGED

    # Fast path: try record()
    fn = getattr(event_tap, "record", None)
    if callable(fn):
        try:
            fn(ev)
            return
        except Exception as e:
            if AXON_DEBUG:
                print(f"[SenseLoop] tap.record error: {e}")

    # Fallback: try tap()
    fn = getattr(event_tap, "tap", None)
    if callable(fn):
        try:
            fn(ev)
            return
        except Exception as e:
            if AXON_DEBUG:
                print(f"[SenseLoop] tap.tap error: {e}")

    # Final fallback: log once, then noop
    if AXON_DEBUG and not _TAP_FIRST_FAILURE_LOGGED:
        print(
            "[SenseLoop] no event tap available (expected event_tap.record(ev) or event_tap.tap(ev)); continuing without debug ring.",
        )
        _TAP_FIRST_FAILURE_LOGGED = True


def _iter_pullable_drivers() -> Iterable[DriverInterface]:
    """
    Yields driver instances that implement 'pull'.
    Favors the shared registry, falls back to nothing (safe).
    """
    if not get_driver_registry:
        return []
    try:
        reg = get_driver_registry()
    except Exception:
        return []

    yielded: list[DriverInterface] = []

    get = getattr(reg, "get", None)
    has = getattr(reg, "has", None)
    drivers_map = getattr(reg, "drivers", None)

    # Try explicit names first (cheap + avoids abstract drivers)
    for name in ("rss", "qora_search"):
        try:
            if callable(has) and not has(name):
                continue
            d = get(name) if callable(get) else None
            if d and hasattr(d, "pull"):
                yielded.append(d)
        except Exception:
            continue

    # Fallback to scanning the dict if nothing found
    if not yielded and isinstance(drivers_map, dict):
        for d in drivers_map.values():
            if hasattr(d, "pull"):
                yielded.append(d)

    return yielded


async def _iter_registry_events() -> AsyncIterator:
    """
    Iterates events from the Source Registry (if available and enabled).
    Uses the registry/feeds.py ingestor (RSS/JSON/etc.) and yields AxonEvents.
    """
    if not USE_REGISTRY or SourceRegistryIngestor is None:
        if AXON_DEBUG and not USE_REGISTRY:
            print("[SenseLoop] registry disabled via AXON_USE_REGISTRY=0")
        if AXON_DEBUG and SourceRegistryIngestor is None:
            print("[SenseLoop] registry module unavailable; skipping")
        if False:
            yield  # pragma: no cover (make this an async generator)
        return

    ingestor = SourceRegistryIngestor(REG_PATH_MAIN, REG_PATH_LOCAL)
    try:
        # Hot-reload if changed
        await ingestor.refresh()

        # --- DIAGNOSTIC: show enabled source counts and a few examples
        if AXON_DEBUG:
            try:
                rss = ingestor.reg.iter_enabled("rss")
                jsf = ingestor.reg.iter_enabled("jsonfeed")
                jsn = ingestor.reg.iter_enabled("json")
                csv = ingestor.reg.iter_enabled("csv")
                ics = ingestor.reg.iter_enabled("ics")
                mqtt = ingestor.reg.iter_enabled("mqtt")
                print(
                    f"[Registry] enabled rss={len(rss)} jsonfeed={len(jsf)} json={len(jsn)} csv={len(csv)} ics={len(ics)} mqtt={len(mqtt)}",
                )
                if rss:
                    preview = ", ".join(f"{s.id}→{(s.url or '')[:60]}" for s in rss[:3])
                    print(f"[Registry] rss preview: {preview}")
            except Exception as _e:
                print(f"[Registry] diag failed: {_e}")

        count = 0
        async for ev in ingestor.iter_events():
            yield ev
            count += 1
            if MAX_REGISTRY_EVENTS_PER_TICK and count >= MAX_REGISTRY_EVENTS_PER_TICK:
                if AXON_DEBUG:
                    print(
                        f"[SenseLoop] registry cap reached: {count} >= {MAX_REGISTRY_EVENTS_PER_TICK}",
                    )
                break
    except Exception as e:
        if AXON_DEBUG:
            print(f"[SenseLoop] registry ingest error: {e}")
        if False:
            yield  # pragma: no cover


class SenseLoop:
    """
    Polls pull-only drivers and (optionally) the registry-based ingestor,
    then forwards canonical events to:
      - the in-memory tap (for /axon/recent)
      - the event bus (optional)
    """

    def __init__(self) -> None:
        self._publish = PUBLISH_EVENTS

    async def _handle_event(self, ev, source_name: str) -> None:
        # 1) Record to the tap so /axon/recent shows something (resilient helper)
        _emit_to_tap(ev)

        # 2) Optionally publish to the bus for downstream systems
        if self._publish:
            try:
                await event_bus.publish("axon.event", ev)
            except Exception as bus_err:
                if AXON_DEBUG:
                    print(f"[SenseLoop] bus publish error ({source_name}): {bus_err}")

    async def _poll_drivers_once(self, remaining_budget: int) -> int:
        if remaining_budget <= 0:
            return 0

        total = 0
        for drv in _iter_pullable_drivers():
            if remaining_budget <= 0:
                break

            name = getattr(drv, "NAME", drv.__class__.__name__.lower())
            per_driver = 0
            try:
                # No params → let the driver use env defaults (feed URL, warmup, etc.)
                async for ev in drv.pull({}):
                    await self._handle_event(ev, name)
                    total += 1
                    per_driver += 1
                    remaining_budget -= 1
                    if MAX_DRIVER_EVENTS_PER_DRIVER and per_driver >= MAX_DRIVER_EVENTS_PER_DRIVER:
                        if AXON_DEBUG:
                            print(
                                f"[SenseLoop] per-driver cap reached for {name}: {per_driver} >= {MAX_DRIVER_EVENTS_PER_DRIVER}",
                            )
                        break
                    if remaining_budget <= 0:
                        break
            except Exception as e:
                if AXON_DEBUG:
                    print(f"[SenseLoop] driver '{name}' pull error: {e}")

        return total

    async def _poll_registry_once(self, remaining_budget: int) -> int:
        if remaining_budget <= 0:
            return 0

        total = 0
        async for ev in _iter_registry_events():
            await self._handle_event(ev, "registry")
            total += 1
            remaining_budget -= 1
            if remaining_budget <= 0:
                break
        return total

    async def poll_once(self) -> int:
        """
        One “tick”: poll drivers + registry (if enabled), respecting caps.
        Order: drivers first (to preserve existing behavior), then registry.
        """
        budget = MAX_EVENTS_PER_TICK if MAX_EVENTS_PER_TICK > 0 else 10**9

        # --- DIAGNOSTIC: flags + paths each tick when AXON_DEBUG=1
        if AXON_DEBUG:
            print(
                "[SenseLoop] flags "
                f"USE_REGISTRY={USE_REGISTRY} PUBLISH={self._publish} "
                f"REG_MAIN={REG_PATH_MAIN} REG_LOCAL={REG_PATH_LOCAL} "
                f"MAX_TICK={MAX_EVENTS_PER_TICK} MAX_REG={MAX_REGISTRY_EVENTS_PER_TICK} MAX_PER_DRV={MAX_DRIVER_EVENTS_PER_DRIVER}",
            )

        produced = 0
        # 1) Pull from classic drivers
        n = await self._poll_drivers_once(budget - produced)
        produced += n

        # 2) Pull from registry sources (RSS/JSON/etc.) if enabled
        n = await self._poll_registry_once(budget - produced)
        produced += n

        if AXON_DEBUG:
            print(f"[SenseLoop] tick: produced={produced}")

        return produced
