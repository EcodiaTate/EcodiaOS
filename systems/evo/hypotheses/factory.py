# systems/evo/hypotheses/factory.py
from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from systems.evo.schemas import ConflictNode, Hypothesis


class HypothesisFactory:
    """
    A stateless factory that generates a set of default hypotheses for a
    single, given conflict node. This contains the core generation logic.
    """

    def for_conflict(self, c: ConflictNode) -> list[Hypothesis]:
        mods = c.context.get("modules", [])
        return [
            Hypothesis(
                hypothesis_id=f"hyp_{uuid4().hex[:10]}",
                conflict_ids=[c.conflict_id],
                title=f"Strengthen spec for {', '.join(mods) or 'unknown'}",
                rationale="Spec gaps (temporal/resource/policy) block safe fixes.",
                strategy="spec_first",
                scope_hint={"modules": mods},
                expected_impact={"risk_reduction": 0.3, "clarity": 0.7},
                meta={"conflicts": [c]},
            ),
            Hypothesis(
                hypothesis_id=f"hyp_{uuid4().hex[:10]}",
                conflict_ids=[c.conflict_id],
                title=f"Local bounded fix for {c.conflict_id}",
                rationale="Localized repair guarded by invariants.",
                strategy="local_fix",
                scope_hint={"modules": mods},
                expected_impact={"latency_delta": -0.05, "error_rate_delta": -0.01},
                meta={"conflicts": [c]},
            ),
        ]


class HypothesisService:
    """
    The main service used by the EvoEngine. It depends on a conflict_getter
    function to resolve conflict IDs into full ConflictNode objects before
    passing them to the factory.
    """

    def __init__(self, conflict_getter: Callable[[str], ConflictNode]) -> None:
        self._getter = conflict_getter
        self._factory = HypothesisFactory()

    def spawn(
        self,
        conflict_ids: list[str],
        strategies: list[str] | None = None,
        budget_ms: int | None = None,
    ) -> list[Hypothesis]:
        """
        Spawns hypotheses for a list of conflict IDs.
        """
        hyps: list[Hypothesis] = []
        for cid in conflict_ids:
            # The service uses the injected getter to fetch the full node
            try:
                c = self._getter(cid)
                for h in self._factory.for_conflict(c):
                    if not strategies or h.strategy in strategies:
                        hyps.append(h)
            except KeyError:
                print(f"[HypothesisService] WARN: Could not find conflict_id '{cid}' during spawn.")
                continue
        return hyps
