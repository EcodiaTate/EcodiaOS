# systems/atune/salience/conformal.py
from __future__ import annotations

from collections import deque


class PerHeadConformal:
    """
    Maintains an empirical distribution per salience head and computes p-values.
    Non-parametric: p = rank(score)/N with smoothing.
    """

    def __init__(self, window: int = 512, alpha: float = 0.05):
        self.window = window
        self.alpha = alpha
        self._hist: dict[str, deque[float]] = {}

    def update(self, head: str, score: float) -> None:
        dq = self._hist.setdefault(head, deque(maxlen=self.window))
        dq.append(score)

    def p_value(self, head: str, score: float) -> float:
        dq = self._hist.get(head)
        if not dq:
            # Uncalibrated → neutral p
            return 0.5
        # Rank-based p-value (upper tail)
        greater = sum(1 for s in dq if s >= score)
        return (greater + 1) / (len(dq) + 1)

    def summary(self, scores: dict[str, float]) -> tuple[float, dict[str, float]]:
        pvals = {h: self.p_value(h, v) for h, v in scores.items()}
        p_min = min(pvals.values()) if pvals else 1.0
        return p_min, pvals
