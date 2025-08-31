# systems/atune/metrics/secl_counters.py
from __future__ import annotations

import time
from copy import deepcopy
from threading import RLock
from typing import Any

_lock = RLock()
_counters: dict[str, int] = {}
_gauges: dict[str, float] = {}
_info: dict[str, Any] = {"started_utc": None}


def bump(name: str, inc: int = 1) -> None:
    with _lock:
        _counters[name] = int(_counters.get(name, 0)) + int(inc)


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[name] = float(value)


def set_info(name: str, value: Any) -> None:
    with _lock:
        _info[name] = value
        if _info.get("started_utc") is None:
            _info["started_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "counters": deepcopy(_counters),
            "gauges": deepcopy(_gauges),
            "info": deepcopy(_info),
        }
