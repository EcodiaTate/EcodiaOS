from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from systems.nova.insights.self_model import NovaSelfModel
from systems.nova.novelty.reservoir import NoveltyReservoir
from systems.nova.playbooks.registry import PLAYBOOK_REGISTRY, BasePlaybook  # existing
from systems.nova.runners.meta_playbook import MetaPlaybookComposer
from systems.nova.schemas import InnovationBrief, InventionCandidate
from systems.synapse.schemas import Candidate, TaskContext
from systems.synapse.sdk.client import SynapseClient


class PortfolioRunner(BaseModel):
    """
    Runs a *portfolio* of playbooks with learned budget splits + novelty constraints.
    Backwards compatible: can be used *instead of* PlaybookRunner in propose().
    """

    max_parallel: int = 4

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._synapse = SynapseClient()
        self._self = NovaSelfModel()
        self._novel = NoveltyReservoir()
        # Extend registry with meta-composer on the fly
        self._playbooks: dict[str, BasePlaybook] = {pb.name: pb() for pb in PLAYBOOK_REGISTRY}
        self._playbooks[MetaPlaybookComposer.name] = MetaPlaybookComposer()  # type: ignore

    from core.telemetry.decorators import episode

    async def _pick(self, brief: InnovationBrief) -> list[str]:
        """
        Ask Synapse to rank arms (playbooks); take top-K for this portfolio.
        """
        task = TaskContext(
            task_key=f"nova.portfolio.{brief.brief_id}",
            goal=brief.problem,
            risk_level=brief.constraints.get("risk_tier", "medium"),
            budget="normal",
        )
        arms = [
            Candidate(id=name, content={"desc": f"{name} playbook"})
            for name in self._playbooks.keys()
        ]
        sel = await self._synapse.select_arm(task, candidates=arms)
        # Champion first, but include alternatives (diversity)
        ranking: list[str] = [sel.champion_arm.arm_id] + [
            a.id for a in arms if a.id != sel.champion_arm.arm_id
        ]
        return ranking[: self.max_parallel]

    async def run(
        self,
        brief: InnovationBrief,
        *,
        budget_ms: int = 6000,
        decision_id: str | None = None,
    ) -> list[InventionCandidate]:
        names = await self._pick(brief)
        priors = self._self.priors(
            problem=brief.problem,
            context=brief.context or {},
            playbook_names=names,
        )
        # Split budget proportionally (≥ 500ms minimum per arm)
        splits = {n: max(500, int(budget_ms * priors.get(n, 0))) for n in names}
        # Normalise to not exceed budget_ms
        total = sum(splits.values())
        if total > max(1, budget_ms):
            scale = budget_ms / total
            splits = {k: max(250, int(v * scale)) for k, v in splits.items()}

        async def run_one(name: str) -> list[InventionCandidate]:
            pb = self._playbooks[name]
            cands = await pb.run(brief, splits[name])
            for c in cands:
                c.provenance.update({"portfolio_arm": name, "decision_id": decision_id})
                c.scores["cost_ms"] = c.scores.get("cost_ms", 0) or splits[name]
            return cands

        results = await asyncio.gather(*[run_one(n) for n in names], return_exceptions=False)
        flat: list[InventionCandidate] = [c for sub in results for c in sub]
        # Enforce novelty & cap portfolio size
        filtered = [c for c in flat if self._novel.accept(c.dict())]
        return filtered[: self.max_parallel]
