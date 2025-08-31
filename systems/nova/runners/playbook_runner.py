from __future__ import annotations

import asyncio
import os
from typing import Any

from pydantic import BaseModel

from systems.nova.dsl.lint import LintIssue, lint_mechanism
from systems.nova.dsl.mutate import MechanismMutator
from systems.nova.novelty.reservoir import NoveltyReservoir
from systems.nova.playbooks.hotreload import PlaybookHotReloader
from systems.nova.playbooks.registry import PLAYBOOK_REGISTRY, BasePlaybook
from systems.nova.schemas import InnovationBrief, InventionCandidate


class PlaybookRunner(BaseModel):
    """
    SoC-compliant PlaybookRunner:
      - No selection/learning: Synapse/Atune own that.
      - Ephemeral novelty-only (per-call) to diversify the portfolio.
      - MechanismSpec linting: invalid DAGs are dropped early.
      - Hot-reload playbooks for dev velocity.
      - Optional *local* augmentation (safe DAG mutations) to expand proposals.
    """

    max_parallel: int = 4
    include_meta_composer: bool = True  # If registry already includes it, it's a no-op.
    enable_augmentation: bool = bool(int(os.getenv("NOVA_ENABLE_AUGMENT", "1")))
    max_augment_per_candidate: int = int(os.getenv("NOVA_MAX_AUGMENT_PER_CAND", "1"))

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._hot = PlaybookHotReloader()
        self._playbooks: dict[str, BasePlaybook] = {}
        self._mutator = MechanismMutator()
        self._refresh_registry()

    def _refresh_registry(self) -> None:
        self._hot.check_reload()
        self._playbooks = {pb.name: pb() for pb in PLAYBOOK_REGISTRY}

    async def run(self, brief: InnovationBrief, budget_ms: int = 0) -> list[InventionCandidate]:
        """
        Contract preserved: called by /nova/propose. Budget is simply split;
        Nova does not 'choose' arms—only runs them.
        """
        self._refresh_registry()
        if not self._playbooks:
            return []

        names = list(self._playbooks.keys())[: self.max_parallel]
        # Neutral split; caller/headers remain authoritative at the API layer.
        per_arm_min = 250
        if budget_ms and budget_ms > 0:
            slice_ms = max(per_arm_min, int(budget_ms / max(1, len(names))))
            splits = {n: slice_ms for n in names}
        else:
            splits = {n: 0 for n in names}

        async def run_one(name: str) -> list[InventionCandidate]:
            pb = self._playbooks[name]
            cands = await pb.run(brief, splits[name])
            # Annotate provenance + cost, retain existing scores if set.
            for c in cands:
                c.provenance = dict(c.provenance or {})
                c.provenance.setdefault("portfolio_arm", name)
                c.scores = dict(c.scores or {})
                if "cost_ms" not in c.scores or not c.scores["cost_ms"]:
                    c.scores["cost_ms"] = float(splits[name] or 0)
            return cands

        results = await asyncio.gather(*[run_one(n) for n in names], return_exceptions=False)
        flat: list[InventionCandidate] = [c for sub in results for c in sub]

        # 1) Lint mechanisms and drop invalids
        linted: list[InventionCandidate] = []
        for c in flat:
            try:
                _ = lint_mechanism((c.spec or {}).get("mechanism_graph", {}))
                linted.append(c)
            except LintIssue:
                continue

        # 2) Optional augmentation: produce safe, linted mechanism variants
        augmented: list[InventionCandidate] = []
        if self.enable_augmentation and self.max_augment_per_candidate > 0:
            for c in linted:
                augmented.append(c)
                try:
                    for _ in range(self.max_augment_per_candidate):
                        variant = self._mutator.augment_candidate(c)
                        if variant is not None:
                            augmented.append(variant)
                except Exception:
                    # Augmentation is best-effort; never break propose()
                    pass
        else:
            augmented = linted

        # 3) Intra-call novelty filter to push diversity (no persistence)
        bag: list[InventionCandidate] = []
        novelty = NoveltyReservoir()
        for c in augmented:
            if novelty.accept(c.dict()):
                bag.append(c)
            if len(bag) >= self.max_parallel:
                break

        return bag
