# systems/synk/core/switchboard/gatekit.py
from __future__ import annotations

import asyncio
import functools
import random
from collections.abc import Awaitable, Callable
from typing import Any

# only used if you call route_gate from FastAPI routes
try:
    from fastapi import Depends, HTTPException
except Exception:  # if FastAPI isn't present in this process, ignore; route_gate won't be used
    Depends = None
    HTTPException = None  # type: ignore

# shared Switchboard instance
from systems.synk.core.switchboard.runtime import sb


# ---------- 1) Smallest: boolean check ----------
async def gate(flag_key: str, default: bool = False) -> bool:
    """Return True if enabled, else False; fails open to `default` on any error."""
    try:
        return await sb.get_bool(flag_key, default)
    except Exception:
        return default


# ---------- 2) FastAPI route gate ----------
def route_gate(
    flag_key: str,
    default: bool = False,
    *,
    status_code: int = 403,
    detail: str | None = None,
):
    if Depends is None or HTTPException is None:
        raise RuntimeError("route_gate requires FastAPI to be installed/importable")

    async def _dep():
        if not await gate(flag_key, default):
            raise HTTPException(status_code, detail or f"Feature '{flag_key}' is disabled")

    return Depends(_dep)


# ---------- 3) Decorators for functions/tools ----------
def gated_async(flag_key: str, default: bool = False, *, ret: Any = None):
    """Use on async functions: returns `ret` when disabled (default: {'status':'disabled','flag':...})."""

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*a, **kw):
            if await gate(flag_key, default):
                return await fn(*a, **kw)
            return ret if ret is not None else {"status": "disabled", "flag": flag_key}

        return wrapper

    return deco


def gated_sync(flag_key: str, default: bool = False, *, ret: Any = None):
    """Use on sync functions. Safe in/out of event loops; falls back to default on errors."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            async def _check():
                return await gate(flag_key, default)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                enabled = asyncio.run(_check())
            else:
                # if a loop exists, run the check within it
                enabled = loop.run_until_complete(_check()) if not loop.is_running() else False
            if enabled or (enabled is False and default and HTTPException is None):
                return fn(*a, **kw)
            return ret if ret is not None else {"status": "disabled", "flag": flag_key}

        return wrapper

    return deco


# ---------- 4) Daemon/loop helper ----------
async def gated_loop(
    task_coro: Callable[[], Awaitable[Any]],
    *,
    enabled_key: str,
    interval_key: str | None = None,
    default_interval: int = 60,
    jitter: float = 0.0,
):
    await asyncio.sleep(random.uniform(0, min(5, default_interval)))  # small stagger
    while True:
        try:
            if await gate(enabled_key, True):
                try:
                    await task_coro()
                except Exception:
                    pass  # never crash the loop
            interval = default_interval
            if interval_key:
                try:
                    interval = await sb.get_int(interval_key, default_interval)
                except Exception:
                    interval = default_interval
        finally:
            if jitter:
                interval += random.uniform(-jitter, jitter)
            await asyncio.sleep(max(1, interval))
