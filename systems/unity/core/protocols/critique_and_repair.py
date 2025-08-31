# systems/unity/core/protocols/critique_and_repair.py
from enum import Enum, auto
from typing import Any

from core.services.synapse import synapse
from systems.unity.core.neo import graph_writes
from systems.unity.core.room.adjudicator import Adjudicator
from systems.unity.schemas import DeliberationSpec, VerdictModel


class ProtocolState(Enum):
    PROPOSE = auto()
    CRITIQUE = auto()
    REPAIR = auto()
    CROSS_EXAM = auto()
    ADJUDICATE = auto()
    COMPLETE = auto()


class CritiqueAndRepairProtocol:
    def __init__(
        self,
        spec: DeliberationSpec,
        deliberation_id: str,
        episode_id: str,
        panel: list[str],
    ):
        self.spec = spec
        self.deliberation_id = deliberation_id
        self.episode_id = episode_id
        self.panel = panel
        self.state = ProtocolState.PROPOSE
        self.adjudicator = Adjudicator()
        self.synapse = synapse
        self.turn = 0
        self.proposal: dict[str, Any] = {}
        self.critiques: dict[str, str] = {}
        self.repair: dict[str, Any] = {}
        self._artifact_ids: dict[str, str] = {}

    async def _add_transcript(self, role: str, content: str):
        self.turn += 1
        await graph_writes.record_transcript_chunk(self.deliberation_id, self.turn, role, content)

    async def _run_state_propose(self):
        await self._add_transcript("Orchestrator", "Entering PROPOSAL phase.")
        self.proposal["text"] = "This is the initial proposed solution to the problem."
        await self._add_transcript("Proposer", self.proposal["text"])
        # Persist proposal draft artifact
        pid = await graph_writes.create_artifact(
            self.deliberation_id,
            "proposal_draft",
            {"text": self.proposal["text"]},
        )
        self._artifact_ids["proposal_draft"] = pid
        self.state = ProtocolState.CRITIQUE

    async def _run_state_critique(self):
        await self._add_transcript("Orchestrator", "Entering CRITIQUE phase.")
        for critic_role in [r for r in self.panel if "Critic" in r]:
            critique_text = (
                f"As the {critic_role}, I've identified a potential flaw in the proposal."
            )
            self.critiques[critic_role] = critique_text
            await self._add_transcript(critic_role, critique_text)
        self.state = ProtocolState.REPAIR

    async def _run_state_repair(self):
        await self._add_transcript("Orchestrator", "Entering REPAIR phase.")
        self.repair["text"] = "This is the revised proposal, addressing all critiques."
        await self._add_transcript("Proposer", self.repair["text"])
        rid = await graph_writes.create_artifact(
            self.deliberation_id,
            "repair_draft",
            {"text": self.repair["text"], "critiques": self.critiques},
        )
        self._artifact_ids["repair_draft"] = rid
        self.state = ProtocolState.CROSS_EXAM

    async def _run_state_cross_exam(self):
        await self._add_transcript("Orchestrator", "Entering CROSS-EXAMINATION phase.")
        attack = "Counter-argument: What if the input data is malformed in this specific way? The repair does not handle this edge case."
        await self._add_transcript("SafetyCritic", attack)
        self.state = ProtocolState.ADJUDICATE

    async def _run_state_adjudicate(self) -> VerdictModel:
        await self._add_transcript("Orchestrator", "Entering ADJUDICATION phase.")
        beliefs = {"Proposer": 0.6, "SafetyCritic": 0.3, "FactualityCritic": 0.7}
        priors = {"Proposer": 0.8, "SafetyCritic": 0.95, "FactualityCritic": 0.9}
        verdict = await self.adjudicator.decide(
            participant_beliefs=beliefs,
            calibration_priors=priors,
            spec_constraints=self.spec.constraints,
        )
        await self._add_transcript("Adjudicator", f"Final Verdict: {verdict.outcome}.")
        self.state = ProtocolState.COMPLETE
        return verdict

    async def run(self) -> dict[str, Any]:
        while self.state != ProtocolState.COMPLETE:
            if self.state == ProtocolState.PROPOSE:
                await self._run_state_propose()
            elif self.state == ProtocolState.CRITIQUE:
                await self._run_state_critique()
            elif self.state == ProtocolState.REPAIR:
                await self._run_state_repair()
            elif self.state == ProtocolState.CROSS_EXAM:
                await self._run_state_cross_exam()
            elif self.state == ProtocolState.ADJUDICATE:
                verdict = await self._run_state_adjudicate()
                return {"verdict": verdict, "artifact_ids": self._artifact_ids}
        return {
            "verdict": VerdictModel(
                outcome="NO_ACTION",
                confidence=0.0,
                uncertainty=1.0,
                dissent="Protocol failed to reach adjudication.",
            ),
            "artifact_ids": self._artifact_ids,
        }
