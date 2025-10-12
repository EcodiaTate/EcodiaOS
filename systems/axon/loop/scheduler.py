# systems/axon/loop/scheduler.py
from __future__ import annotations

import asyncio
import inspect
import os
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from systems.axon.loop.sense import SenseLoop

# ---- Optional event mirror (debug tap) ----------------------------------------
# If you created systems/axon/loop/event_tap.py as suggested, we'll use it.
try:
    from systems.axon.loop.event_tap import tap as _axon_tap  # type: ignore
except Exception:  # pragma: no cover

    def _axon_tap(_ev):  # no-op fallback
        return None


def _should_debug() -> bool:
    return os.getenv("AXON_DEBUG", "0") == "1"


# ---- Poll helper: try to pass a callback if SenseLoop supports it ------------
async def _poll_once_with_tap(loop: SenseLoop, tap_cb: Callable[[Any], None]) -> int | None:
    """
    Calls SenseLoop.poll_once with a best-effort hook so we can mirror events.
    Compatible with multiple possible poll_once signatures:
      - poll_once(on_event=cb) / poll_once(tap=cb) / poll_once(callback=cb) / …
      - poll_once(cb)  (positional)
      - poll_once() returning an iterable of events (we'll tap them)
      - poll_once() returning an int count (we just return it)
    Returns the produced count if known (int), else None.
    """
    # Try common keyword names
    for kw in ("on_event", "tap", "callback", "cb", "mirror"):
        try:
            res = await loop.poll_once(**{kw: tap_cb})  # type: ignore[arg-type]
            return _normalize_poll_result(res, tap_cb)
        except TypeError:
            pass  # wrong signature; try next

    # Try single positional
    try:
        res = await loop.poll_once(tap_cb)  # type: ignore[misc]
        return _normalize_poll_result(res, tap_cb)
    except TypeError:
        pass

    # Fallback: no args
    res = await loop.poll_once()
    return _normalize_poll_result(res, tap_cb)


def _normalize_poll_result(res: Any, tap_cb: Callable[[Any], None]) -> int | None:
    """
    Normalize poll_once result:
      - If it's an int, treat as produced count.
      - If it's an iterable of events, tap each and return len.
      - Else, return None.
    """
    if isinstance(res, int):
        return res

    # If it's an awaitable (rare), don't block here—scheduler expects poll_once awaited already.
    if isinstance(res, Awaitable):
        return None

    # If it's an iterable of events, mirror them
    try:
        from collections.abc import Iterable

        if isinstance(res, Iterable) and not isinstance(res, (str, bytes, dict)):
            cnt = 0
            for ev in res:
                try:
                    tap_cb(ev)
                except Exception:
                    pass
                cnt += 1
            return cnt
    except Exception:
        pass

    return None


# ---- Main scheduler loop ------------------------------------------------------
async def run_sense_forever(period_sec: float = 300.0) -> None:
    """
    Periodically runs the SenseLoop to poll drivers and process events.
    Adds a best-effort mirror of ingested events into the debug ring buffer.
    """
    loop = SenseLoop()
    # Period (with env override)
    base_period = float(os.getenv("AXON_SENSE_PERIOD_SEC", str(period_sec)))
    # Optional jitter to avoid thundering herd (0.0–0.3 recommended)
    jitter_pct = float(os.getenv("AXON_SENSE_JITTER_PCT", "0.0"))
    # First run happens immediately
    immediate_first = os.getenv("AXON_SENSE_IMMEDIATE_FIRST", "1") == "1"

    # Helper for computing next sleep with jitter
    def _next_sleep() -> float:
        if jitter_pct <= 0:
            return base_period
        j = base_period * jitter_pct
        return max(0.0, base_period + random.uniform(-j, j))

    # Run immediately once if configured
    if immediate_first:
        try:
            produced = await _poll_once_with_tap(loop, _axon_tap)
            if _should_debug():
                print(
                    f"[SenseLoop] produced={produced if produced is not None else 'unknown'} (immediate)"
                )
        except Exception as e:
            if _should_debug():
                print(f"[SenseLoop] error on immediate run: {e}")

    # Main periodic loop
    while True:
        try:
            start = time.time()
            produced = await _poll_once_with_tap(loop, _axon_tap)
            took = (time.time() - start) * 1000.0
            if _should_debug():
                print(
                    f"[SenseLoop] produced={produced if produced is not None else 'unknown'} "
                    f"took_ms={took:.1f}",
                )
        except asyncio.CancelledError:
            # Graceful shutdown
            if _should_debug():
                print("[SenseLoop] cancelled; exiting.")
            raise
        except Exception as e:
            if _should_debug():
                print(f"[SenseLoop] error: {e}")

        await asyncio.sleep(_next_sleep())
