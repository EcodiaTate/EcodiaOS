# systems/unity/core/protocols/argument_mining.py
from typing import Any

from core.services.synapse import synapse
from systems.unity.core.neo import graph_writes
from systems.unity.core.room.adjudicator import Adjudicator
from systems.unity.core.room.argument_map import ArgumentMiner
from systems.unity.schemas import DeliberationSpec, VerdictModel


class ArgumentMiningProtocol:
    def __init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str):
        self.spec = spec
        self.deliberation_id = deliberation_id
        self.episode_id = episode_id
        self.adjudicator = Adjudicator()
        self.synapse = synapse
        self.miner = ArgumentMiner()
        self.turn = 0
        self._artifact_ids: dict[str, str] = {}

    async def _add_transcript(self, role: str, content: str):
        self.turn += 1
        await graph_writes.record_transcript_chunk(self.deliberation_id, self.turn, role, content)

    async def run(self) -> dict[str, Any]:
        await self._add_transcript("Orchestrator", "Starting Argument Mining protocol.")

        # Simulated rationales (replace with Synapse generations as needed)
        num_rationales = 3
        rationales = []
        for i in range(num_rationales):
            simulated = {
                "conclusion": "APPROVE",
                "claims": {
                    f"c{i}_1": "The proposal is cost-effective.",
                    f"c{i}_2": "The data supports the main premise.",
                    f"c{i}_3": "The long-term benefits outweigh the risks.",
                },
                "inferences": [
                    {"from": f"c{i}_1", "to": f"c{i}_3", "type": "SUPPORTS"},
                    {"from": f"c{i}_2", "to": f"c{i}_3", "type": "SUPPORTS"},
                ],
            }
            rationales.append(simulated)
            await self._add_transcript(
                f"RationaleBot_{i + 1}",
                f"Generated rationale concluding {simulated['conclusion']}.",
            )

        await self._add_transcript(
            "ArgumentMiner",
            "Building unified argument graph from rationales.",
        )
        conclusion_id = "final_conclusion"
        self.miner.add_claim(conclusion_id, "The proposal should be approved.")

        for r_idx, r in enumerate(rationales):
            for claim_id, text in r["claims"].items():
                self.miner.add_claim(claim_id, text)
            for inf in r["inferences"]:
                self.miner.add_inference(inf["from"], inf["to"], inf["type"])
            sub = f"c{r_idx}_3"
            if sub in r["claims"]:
                self.miner.add_inference(sub, conclusion_id, "SUPPORTS")

        assumption_ids = list(
            dict.fromkeys(self.miner.get_minimal_assumption_set(conclusion_id)),
        )  # preserve first-seen order, remove dups
        assumption_texts = []
        for aid in assumption_ids:
            node = self.miner.claims.get(aid)
            if node and "text" in node:
                if node["text"] not in assumption_texts:
                    assumption_texts.append(node["text"])
        await self._add_transcript("ArgumentMiner", f"Minimal assumption set: {assumption_texts}")

        # Persist argument_map artifact
        graph_snapshot = {
            "claims": self.miner.claims,
            "supports": list(self.miner._sup_out.items()),
            "attacks": list(self.miner._atk_out.items()),
            "conclusion": conclusion_id,
            "assumptions": assumption_ids,  # use the deduped IDs
        }

        argmap_id = await graph_writes.create_artifact(
            self.deliberation_id,
            "argument_map",
            graph_snapshot,
        )
        self._artifact_ids["argument_map"] = argmap_id

        verdict = VerdictModel(
            outcome="APPROVE",
            confidence=0.9,
            uncertainty=0.1,
            dissent=f"Decision rests on assumptions: {', '.join(assumption_texts)}",
        )
        await self._add_transcript("Adjudicator", f"Verdict reached: {verdict.outcome}.")
        return {"verdict": verdict, "artifact_ids": self._artifact_ids}
