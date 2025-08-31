# systems/atune/salience/engine.py

import asyncio
from typing import Any

import numpy as np

from systems.atune.processing.canonical import CanonicalEvent
from systems.atune.salience.heads import SalienceHead, SalienceScore


class SalienceEngine:
    """
    Manages and executes salience heads, now modulated by dynamic
    gating weights from the Meta-Attention Gater (MAG).
    """

    def __init__(self, heads: list[SalienceHead]):
        self._heads = sorted(heads, key=lambda h: h.name)
        self.head_names = [h.name for h in self._heads]
        if len(set(self.head_names)) != len(self._heads):
            raise ValueError("All salience heads must have a unique name.")

    async def run_heads(
        self,
        event: CanonicalEvent,
        gating_vector: np.ndarray,
        priors: dict[str, Any] | None = None,  # accepted for compatibility; currently unused
    ) -> dict[str, Any]:
        """
        Runs all registered salience heads and applies the MAG gating
        vector to their raw scores.
        """
        if not self._heads:
            return {}
        if len(gating_vector) != len(self._heads):
            raise ValueError("Gating vector dimension must match the number of heads.")

        tasks = [head.score(event) for head in self._heads]
        raw_scores: list[SalienceScore] = await asyncio.gather(*tasks)

        raw_scores_dict = {s.head_name: s for s in raw_scores}
        sorted_raw_scores = [raw_scores_dict[name] for name in self.head_names]

        weighted_scores = {
            res.head_name: {
                "raw_score": res.score,
                "gate_weight": gating_vector[i],
                "final_score": res.score * gating_vector[i],
                "details": res.details,
            }
            for i, res in enumerate(sorted_raw_scores)
        }
        return weighted_scores
