from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from hashlib import blake2s
from typing import Any


@dataclass
class ArmStats:
    trials: int = 0
    wins: int = 0
    spend_ms: int = 0
    score_sum: float = 0.0  # e.g., fae/uplift composite
    last_ts: float = field(default_factory=time.time)


def _h16(obj: object) -> str:
    return blake2s(repr(obj).encode("utf-8")).hexdigest()[:16]


class NovaSelfModel:
    """
    Non-parametric, robust bandit memory:
      - Keys by (problem_signature, playbook_name)
      - Tracks win-rate, average score, cost, recency
      - Produces budget priors, UCB-style explore bonuses
    """

    def __init__(self) -> None:
        self._arms: dict[tuple[str, str], ArmStats] = {}

    def _sig(self, problem: str, ctx: dict[str, Any]) -> str:
        # Conservative signature: problem text + coarse context hints
        coarse = {k: ctx.get(k) for k in ("domain", "risk_tier", "scale", "targets")}
        return _h16({"p": problem[:512], "c": coarse})

    def update(
        self,
        *,
        problem: str,
        context: dict[str, Any],
        playbook: str,
        won: bool,
        score: float,
        spend_ms: int,
    ) -> None:
        key = (self._sig(problem, context), playbook)
        st = self._arms.setdefault(key, ArmStats())
        st.trials += 1
        st.wins += int(bool(won))
        st.score_sum += float(score)
        st.spend_ms += int(spend_ms)
        st.last_ts = time.time()

    def priors(
        self,
        *,
        problem: str,
        context: dict[str, Any],
        playbook_names: list[str],
    ) -> dict[str, float]:
        """
        Returns a normalised prior weight per playbook.
        Uses UCB-ish confidence + score efficiency.
        """
        sig = self._sig(problem, context)
        priors: dict[str, float] = {}
        total = 0.0
        t_global = sum(self._arms.get((sig, pb), ArmStats()).trials for pb in playbook_names) + 1
        for pb in playbook_names:
            st = self._arms.get((sig, pb), ArmStats())
            mean = (st.score_sum / max(1, st.trials)) if st.trials else 0.0
            ucb = math.sqrt(2.0 * math.log(t_global) / max(1, st.trials)) if st.trials else 1.0
            efficiency = mean / (1.0 + (st.spend_ms / max(1, st.trials)) / 1000.0)
            weight = max(1e-6, 0.15 * ucb + 0.85 * max(0.0, efficiency))
            priors[pb] = weight
            total += weight
        if total <= 0:
            return {pb: 1.0 / max(1, len(playbook_names)) for pb in playbook_names}
        return {pb: w / total for pb, w in priors.items()}
