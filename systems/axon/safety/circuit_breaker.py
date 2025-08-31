# systems/axon/safety/circuit_breaker.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Deque, Dict, Tuple
from collections import deque


@dataclass
class _Sample:
    ts: float
    ok: bool


class CircuitBreaker:
    """
    Time-window breaker evaluated per capability.
    Opens when success ratio falls below threshold OR burst failures exceed cap.
    """

    def __init__(self, window_sec: int = 60, min_success: float = 0.80, burst_fail_cap: int = 5, cooldown_sec: int = 30) -> None:
        self._hist: Dict[str, Deque[_Sample]] = {}
        self._open_until: Dict[str, float] = {}
        self._window = float(window_sec)
        self._min_success = float(min_success)
        self._burst_cap = int(burst_fail_cap)
        self._cooldown = float(cooldown_sec)

    def allow(self, capability: str) -> bool:
        now = time.time()
        until = self._open_until.get(capability, 0.0)
        return now >= until

    def report(self, capability: str, ok: bool) -> None:
        now = time.time()
        q = self._hist.setdefault(capability, deque())
        q.append(_Sample(ts=now, ok=ok))
        # drop old
        while q and (now - q[0].ts) > self._window:
            q.popleft()

        # evaluate
        if not q:
            return
        sr = sum(1 for s in q if s.ok) / len(q)
        burst = 0
        for s in reversed(q):
            if not s.ok:
                burst += 1
            else:
                break
        if sr < self._min_success or burst >= self._burst_cap:
            self._open_until[capability] = now + self._cooldown
