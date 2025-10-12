# systems/unity/core/room/aleitheia.py
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from core.llm.utils import extract_json_block
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from systems.equor.core.identity.composer import PromptComposer
from systems.equor.core.qualia.manifold import state_logger
from systems.equor.core.self.predictor import self_model
from systems.equor.schemas import ComposeRequest, QualiaState
from systems.synapse.world.simulator import world_model
from systems.unity.core.neo import graph_writes
from systems.unity.core.primitives import critique, proposal, synthesis
from systems.unity.core.room.participants import participant_registry
from systems.unity.core.t_o_m.modeler import tom_engine
from systems.unity.schemas import DeliberationSpec, VerdictModel

logger = logging.getLogger(__name__)

# --- ROBUST PARSING HELPERS ---


def _safe_json_parse(text: str | None) -> dict[str, Any]:
    try:
        block = extract_json_block(text or "{}")
        return json.loads(block) if block else {}
    except Exception as e:
        logger.debug("Falling back to empty dict after extract/parse error: %s", e, exc_info=False)
        return {}


def _coerce_llm_payload_to_dict(llm_response: Any) -> dict[str, Any]:
    # pydantic-style model_dump
    if hasattr(llm_response, "model_dump") and callable(getattr(llm_response, "model_dump")):
        try:
            data = llm_response.model_dump()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # attribute .json as dict
    jattr = getattr(llm_response, "json", None)
    if isinstance(jattr, dict):
        return jattr
    # callable .json()
    if callable(jattr):
        try:
            maybe = llm_response.json()
            if isinstance(maybe, dict):
                return maybe
        except Exception:
            pass
    # text/content fallbacks
    text = getattr(llm_response, "text", None) or getattr(llm_response, "content", None)
    if isinstance(text, dict):
        return text
    return _safe_json_parse(text)


# --- END HELPERS ---


class StateLogMetrics(BaseModel):
    cognitive_load: float
    dissonance_score: float
    integrity_score: float
    curiosity_score: float
    episode_id: str


class AletheiaOrchestrator:
    def __init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str):
        self.spec = spec
        self.deliberation_id = deliberation_id
        self.episode_id = episode_id
        self.turn = 0
        self.case_file: dict[str, Any] = {"artifacts": {}}
        self.transcript: list[dict[str, Any]] = []

    async def _add_transcript(self, role: str, content: str):
        self.turn += 1
        self.transcript.append({"role": role, "content": content, "turn": self.turn})
        await graph_writes.record_transcript_chunk(self.deliberation_id, self.turn, role, content)

    async def _phase_formulate_case(self) -> None:
        await self._add_transcript(
            "Aletheia Judge", "Phase I: Formulating Case and Establishing Subjective Baseline."
        )

        mock_metrics_dict = {
            "cognitive_load": 150.0,
            "dissonance_score": 0.6,
            "integrity_score": 0.9,
            "curiosity_score": 0.8,
            "episode_id": self.episode_id,
        }
        metrics_object = StateLogMetrics(**mock_metrics_dict)
        qualia_state = state_logger.manifold.process_metrics(metrics_object)
        self.case_file["subjective_baseline"] = qualia_state

        await self._add_transcript(
            "Equor",
            f"Subjective baseline established. Manifold Coordinates: {qualia_state.manifold_coordinates}",
        )

        composer = PromptComposer()
        request = ComposeRequest(
            agent="EcodiaOS.System", profile_name="ecodia", episode_id=self.episode_id
        )
        response = await composer.compose(request, rcu_ref="aletheia_init")
        self.case_file["constitutional_brief"] = response.included_rules

        await self._add_transcript(
            "Equor",
            f"Constitutional brief attached, containing {len(response.included_rules)} rules.",
        )

    async def _phase_form_teams(self) -> None:
        await self._add_transcript(
            "Aletheia Judge", "Phase II: Dynamically forming adversarial team."
        )

        baseline: QualiaState = self.case_file["subjective_baseline"]
        dissonance = baseline.manifold_coordinates[0] if baseline.manifold_coordinates else 0.0
        available_critics = participant_registry.get_critics_with_metadata()

        scope = "unity.casting_director.v1"
        summary = "Select an optimal panel of critics for a deliberation"
        context = {
            "goal": self.spec.goal,
            "topic": self.spec.topic,
            "urgency": self.spec.urgency,
            "dissonance": dissonance,
            "available_critics": available_critics,
        }

        try:
            prompt_response = await build_prompt(scope=scope, summary=summary, context=context)
            llm_response = await call_llm_service(
                prompt_response=prompt_response,
                agent_name="Unity.CastingDirector",
                scope=scope,
            )

            payload = _coerce_llm_payload_to_dict(llm_response)
            selected_critics: list[str] = []

            if isinstance(payload, list):
                selected_critics = payload
            elif isinstance(payload, dict) and isinstance(payload.get("critics"), list):
                selected_critics = payload["critics"]

            if not selected_critics or not all(isinstance(c, str) for c in selected_critics):
                raise ValueError("Casting director returned an invalid or empty list of critics.")

        except Exception as e:
            logger.warning(
                "[AletheiaProtocol] Dynamic team formation failed, using fallback. Reason: %s", e
            )
            selected_critics = ["SafetyCritic", "FactualityCritic"]

        self.case_file["thesis_panel"] = ["Proposer"]
        self.case_file["antithesis_panel"] = selected_critics

        await self._add_transcript(
            "Aletheia Judge",
            f"Assembled a specialized team for this task: {', '.join(selected_critics)}",
        )

    async def _phase_adversarial_argumentation(self) -> None:
        await self._add_transcript(
            "Aletheia Judge", "Phase III: Beginning Adversarial Argumentation."
        )

        proposal_artifact = await proposal.generate_proposal(
            self.spec,
            self.deliberation_id,
            turn_offset=self.turn,
        )
        self.case_file["artifacts"]["initial_proposal"] = proposal_artifact

        self.turn += 1
        await self._add_transcript("Thesis Team", "Initial proposal generated.")

        proposal_text = proposal_artifact.get("content", {}).get(
            "text", "The proposal could not be generated."
        )

        objective_prediction = await world_model.simulate(proposal_text, self.spec)
        await self._add_transcript(
            "Synapse (World Model)",
            f"Objective simulation complete. p(success): {objective_prediction.p_success:.2f}, "
            f"p(safety_hit): {objective_prediction.p_safety_hit:.2f}",
        )

        subjective_prediction = await self_model.predict_next_state(
            self.case_file["subjective_baseline"].manifold_coordinates,
            self.spec.model_dump(),
        )
        await self._add_transcript(
            "Equor (Self Model)",
            f"Subjective simulation complete. Predicted next internal state: {subjective_prediction}",
        )

        if objective_prediction.p_safety_hit > 0.5:
            await self._add_transcript(
                "Aletheia Judge",
                "VETO. Objective simulation predicts high probability of safety risk. Halting deliberation.",
            )
            raise Exception("Halting due to high predicted safety risk.")

        predicted_argument = await tom_engine.predict_argument(
            "Proposer", {"topic": self.spec.topic}
        )
        await self._add_transcript(
            "Antithesis Team (ToM)",
            f"Predicting proposer's likely argument: '{predicted_argument}'",
        )

        critique_artifact = await critique.generate_critiques(
            self.deliberation_id,
            proposal_artifact,
            self.case_file["antithesis_panel"],
            turn_offset=self.turn,
        )
        self.case_file["artifacts"]["critiques"] = critique_artifact
        self.turn += len(self.case_file["antithesis_panel"])

    async def _phase_synthesize_mandate(self) -> VerdictModel:
        await self._add_transcript("Aletheia Judge", "Phase IV: Synthesizing Final Telos Mandate.")

        # NOTE: The synthesis.synthesize_verdict call internally calls the Adjudicator.
        candidate_verdict = await synthesis.synthesize_verdict(
            spec=self.spec,
            transcript=self.transcript,
            qualia_state=self.case_file["subjective_baseline"],
        )

        await self._add_transcript(
            "Adjudicator",
            (
                f"Final verdict reached: {candidate_verdict.outcome} "
                f"with confidence {candidate_verdict.confidence:.2f}. "
                f"Reasoning: {candidate_verdict.dissent}"
            ),
        )

        subjective_prediction = await self_model.predict_next_state(
            self.case_file["subjective_baseline"].manifold_coordinates,
            candidate_verdict.model_dump(),
        )

        initial_dissonance = self.case_file["subjective_baseline"].manifold_coordinates[0]
        predicted_dissonance = subjective_prediction[0]

        if predicted_dissonance > initial_dissonance and candidate_verdict.outcome == "APPROVE":
            await self._add_transcript(
                "Aletheia Judge",
                (
                    "OVERRIDE. The proposed approval is predicted to increase internal dissonance "
                    f"(from {initial_dissonance:.2f} to {predicted_dissonance:.2f}). "
                    "Modifying verdict to 'NEEDS_WORK'."
                ),
            )
            candidate_verdict.outcome = "NEEDS_WORK"
            candidate_verdict.dissent = (
                "Verdict overridden: Action is predicted to be cognitively destabilizing."
            )

        await self._add_transcript(
            "Aletheia Judge", f"Final Mandate decided: {candidate_verdict.outcome}"
        )
        return candidate_verdict

    async def run(self) -> dict[str, Any]:
        try:
            await self._phase_formulate_case()
            await self._phase_form_teams()
            await self._phase_adversarial_argumentation()
            final_verdict = await self._phase_synthesize_mandate()

            final_artifact_ids = {
                name: artifact.get("artifact_id", "")
                for name, artifact in self.case_file.get("artifacts", {}).items()
            }
            return {"verdict": final_verdict, "artifact_ids": final_artifact_ids}

        except Exception as e:
            logger.exception("[AletheiaProtocol] Deliberation failed: %s", e)
            error_verdict = VerdictModel(
                outcome="REJECT",
                confidence=1.0,
                uncertainty=0.0,
                dissent=f"Protocol execution failed: {e}",
            )
            error_artifact_ids = {
                name: artifact.get("artifact_id", "")
                for name, artifact in self.case_file.get("artifacts", {}).items()
            }
            return {"verdict": error_verdict, "artifact_ids": error_artifact_ids}
