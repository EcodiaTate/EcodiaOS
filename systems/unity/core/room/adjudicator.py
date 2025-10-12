# systems/unity/core/room/adjudicator.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from core.llm.utils import extract_json_block
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from systems.unity.schemas import DeliberationSpec, VerdictModel

logger = logging.getLogger(__name__)


# --------------------------- Models ---------------------------


class AdjudicatorOutput(BaseModel):
    """
    JSON contract expected from the Adjudicator LLM.
    """

    outcome: Literal["APPROVE", "REJECT", "NEEDS_WORK", "NO_ACTION"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., description="Concise justification for the outcome.")
    followups: list[str] = Field(default_factory=list, description="Actionable follow-up tasks.")


# ----------------------- Helper Functions ----------------------


def _format_transcript_for_prompt(transcript: list[dict[str, Any]]) -> str:
    """
    Converts the deliberation transcript (list of dicts) into a readable string.
    """
    return "\n".join(
        f"### {turn.get('role', 'Unknown')} (Turn {turn.get('turn', 0)})\n{turn.get('content', '')}\n"
        for turn in transcript
    )


def _safe_json_parse(text: str | None) -> dict[str, Any]:
    """
    Best-effort parse of a JSON object embedded in free text.
    Uses extract_json_block() and falls back to {} on failure.
    """
    try:
        block = extract_json_block(text or "{}")
        return json.loads(block) if block else {}
    except Exception as e:
        logger.debug("Falling back to empty dict after extract/parse error: %s", e, exc_info=False)
        return {}


def _coerce_llm_payload_to_dict(llm_response: Any) -> dict[str, Any]:
    """
    The gateway may return different shapes. Normalize to a plain dict.
    """
    # Case 1: Pydantic-style object
    if hasattr(llm_response, "model_dump") and callable(getattr(llm_response, "model_dump")):
        try:
            data = llm_response.model_dump()
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.debug("model_dump() failed on llm_response: %s", e, exc_info=False)

    # Case 2: Already a dict-like attribute named 'json'
    if hasattr(llm_response, "json") and isinstance(getattr(llm_response, "json"), dict):
        try:
            return getattr(llm_response, "json")
        except Exception:
            pass

    # Case 3: Object exposing .json() method
    if hasattr(llm_response, "json") and callable(getattr(llm_response, "json")):
        try:
            maybe = llm_response.json()
            if isinstance(maybe, dict):
                return maybe
        except Exception as e:
            logger.debug(".json() callable on llm_response failed: %s", e, exc_info=False)

    # Case 4: The response might expose text/content
    text = getattr(llm_response, "text", None)
    if not text:
        text = getattr(llm_response, "content", None)

    # If text itself is a dict (from some response wrappers), handle that before parsing
    if isinstance(text, dict):
        return text

    return _safe_json_parse(text)


# -------------------------- Service ---------------------------


class Adjudicator:
    """
    Rule-aware service that determines the final verdict of a deliberation
    by synthesizing the full transcript with an LLM.
    """

    _instance: Adjudicator | None = None

    def __new__(cls) -> Adjudicator:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def decide(
        self,
        spec: DeliberationSpec,
        transcript: list[dict[str, Any]],
    ) -> VerdictModel:
        """
        Make a final decision by prompting an LLM with the full context and transcript.
        Returns a VerdictModel; on any failure, returns a conservative REJECT verdict.
        """
        transcript_text = _format_transcript_for_prompt(transcript)

        scope = "unity.judge.decision"
        summary = "Synthesize deliberation transcript into a final verdict."
        context = {
            "deliberation_spec": spec.model_dump(),
            "transcript_text": transcript_text,
        }

        try:
            prompt_response = await build_prompt(
                scope=scope,
                summary=summary,
                context=context,
            )
            llm_response = await call_llm_service(
                prompt_response=prompt_response,
                agent_name="Unity.Adjudicator",
                scope=scope,
            )

            # Normalize potentially complex response into a clean dictionary.
            data = _coerce_llm_payload_to_dict(llm_response)

            # Validate the clean dictionary directly.
            adjudicator_output = AdjudicatorOutput.model_validate(data)

            uncertainty = 1.0 - adjudicator_output.confidence
            return VerdictModel(
                outcome=adjudicator_output.outcome,
                confidence=adjudicator_output.confidence,
                uncertainty=uncertainty,
                dissent=adjudicator_output.reasoning,
                followups=adjudicator_output.followups,
            )
        except ValidationError as ve:
            logger.error("[Adjudicator] Output validation failed: %s", ve, exc_info=True)
            return VerdictModel(
                outcome="REJECT",
                confidence=1.0,
                uncertainty=0.0,
                dissent=f"Adjudication failed: invalid LLM output schema: {ve}",
                followups=[],
            )
        except Exception as e:
            logger.error("[Adjudicator] Decision failed: %s", e, exc_info=True)
            return VerdictModel(
                outcome="REJECT",
                confidence=1.0,
                uncertainty=0.0,
                dissent=f"Adjudication failed due to an internal error: {e}",
                followups=[],
            )
