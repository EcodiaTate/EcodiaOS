# systems/atune/focus/tuner.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiffusionTuner:
    """
    Hint-driven tuner: Atune does not learn; Synapse tells us the leak_gamma.
    """

    leak_gamma: float = 0.15
    min_g: float = 0.02
    max_g: float = 0.6

    def apply_hint(self, leak_gamma: float | None) -> float:
        if leak_gamma is None:
            return self.leak_gamma
        g = float(leak_gamma)
        g = max(self.min_g, min(self.max_g, g))
        self.leak_gamma = g
        return self.leak_gamma
