from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from core.llm.bus import event_bus


async def publish(event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Works whether bus.publish expects (name,payload) or (single dict)."""
    fn = getattr(event_bus, "publish", None)
    if not fn:
        return
    payload = payload or {}
    try:
        if inspect.signature(fn).parameters.keys() >= {"event_type", "payload"}:
            # publish(event_type=..., payload=...)
            r = fn(event_type=event_type, payload=payload)
        else:
            # publish(event_type, payload)
            r = fn(event_type, payload)  # type: ignore[misc]
        if inspect.isawaitable(r):
            await r
    except TypeError:
        # Fallback to publish({...})
        r = fn({"event": event_type, **payload})  # type: ignore[misc]
        if inspect.isawaitable(r):
            await r


def subscribe(event_type: str, callback: Callable[[dict[str, Any]], Any | Awaitable[Any]]):
    return event_bus.subscribe(event_type, callback)
