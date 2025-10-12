# systems/axon/loop/event_tap.py
from __future__ import annotations

import os
from collections import deque

RECENT_AXON_EVENTS = deque(maxlen=int(os.getenv("AXON_DEBUG_RING_MAX", "200")))


def tap(event) -> None:
    """Mirror any AxonEvent for quick inspection."""
    try:
        RECENT_AXON_EVENTS.append(event)
    except Exception:
        # Don’t let debug get in the way of prod
        pass


def dump(limit: int = 20):
    out = []
    for e in list(RECENT_AXON_EVENTS)[-limit:][::-1]:
        md = getattr(e, "model_dump", None)
        if callable(md):
            out.append(md())
        else:
            try:
                out.append(e.__dict__)
            except Exception:
                out.append({"repr": repr(e)})
    return out
