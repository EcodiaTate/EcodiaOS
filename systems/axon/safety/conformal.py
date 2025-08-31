# systems/axon/safety/conformal.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Deque
from collections import deque


@dataclass
class ConformalBound:
    lower: float
    upper: float
    n: int


class ConformalPredictor:
    """
    Simple online absolute residual collector with quantile bound.
    Not statistically perfect, but fast and robust for gating.
    """

    def __init__(self, max_residuals: int = 512, q: float = 0.9) -> None:
        self._res: Deque[float] = deque(maxlen=max_residuals)
        self._q = max(0.5, min(q, 0.99))

    def observe(self, predicted: float, actual: float) -> None:
        self._res.append(abs(actual - predicted))

    def bound(self, predicted: float) -> ConformalBound:
        if not self._res:
            return ConformalBound(lower=predicted - 1.0, upper=predicted + 1.0, n=0)
        # quantile via sorted slice (fast enough, bounded)
        s = sorted(self._res)
        idx = int(self._q * (len(s) - 1))
        e = s[idx]
        return ConformalBound(lower=predicted - e, upper=predicted + e, n=len(s))
