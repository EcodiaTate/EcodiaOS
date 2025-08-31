# systems/unity/core/protocols/concurrent_competition.py
import asyncio
import time
from typing import Any

import numpy as np

from systems.unity.core.neo import graph_writes
from systems.unity.core.room.adjudicator import Adjudicator
from systems.unity.core.t_o_m.modeler import tom_engine
from systems.unity.core.workspace.global_workspace import global_workspace
from systems.unity.schemas import DeliberationSpec


class ConcurrentCompetitionProtocol:
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
        self.adjudicator = Adjudicator()
        self.active_tasks: list[asyncio.Task] = []
        self._artifact_ids: dict[str, str] = {}

    async def _sub_process(self, role: str, stop_event: asyncio.Event):
        think_cycle = 0
        while not stop_event.is_set():
            think_cycle += 1
            await asyncio.sleep(2 + (np.random.rand() * 2))
            counter_prediction = ""
            if role == "Proposer":
                debate_state = {"topic": self.spec.topic, "proposer_stance": "positive"}
                predicted_argument = tom_engine.predict_argument("SafetyCritic", debate_state)
                counter_prediction = f"PREEMPTIVE COUNTER: I anticipate the SafetyCritic may argue '{predicted_argument}'. My proposal mitigates this by..."
            base_content = (
                f"Insight from {role}, cycle {think_cycle}: Analyzing '{self.spec.topic}'."
            )
            final_content = (
                f"{base_content}\n{counter_prediction}" if counter_prediction else base_content
            )
            salience = 0.5 + (0.4 * (1 if "Critic" in role else 0.5))
            if counter_prediction:
                salience = min(1.0, salience + 0.2)
            await global_workspace.post_cognit(role, final_content, salience)
            if think_cycle > 3:
                break

    async def run(self) -> dict[str, Any]:
        stop_event = asyncio.Event()
        for role in self.panel:
            task = asyncio.create_task(self._sub_process(role, stop_event))
            self.active_tasks.append(task)

        deliberation_duration = 10
        start_time_s = time.time()
        broadcast_count = 0
        while time.time() - start_time_s < deliberation_duration:
            await global_workspace.run_broadcast_cycle()
            broadcast_count += 1
            await asyncio.sleep(1)

        stop_event.set()
        await asyncio.gather(*self.active_tasks, return_exceptions=True)

        final_beliefs = {"SafetyCritic": 0.2, "FactualityCritic": 0.8, "Proposer": 0.7}
        priors = {"SafetyCritic": 0.95, "FactualityCritic": 0.9, "Proposer": 0.8}

        # Persist a workspace summary artifact for replay/analytics
        ws_summary = {
            "broadcast_cycles": broadcast_count,
            "final_beliefs": final_beliefs,
            "priors": priors,
            "topic": self.spec.topic,
        }
        ws_id = await graph_writes.create_artifact(
            self.deliberation_id,
            "workspace_summary",
            ws_summary,
        )
        self._artifact_ids["workspace_summary"] = ws_id

        verdict = await self.adjudicator.decide(final_beliefs, priors, self.spec.constraints)
        return {"verdict": verdict, "artifact_ids": self._artifact_ids}
