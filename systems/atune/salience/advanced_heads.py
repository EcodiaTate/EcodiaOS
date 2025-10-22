# systems/atune/salience/advanced_heads.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import numpy as np
from pydantic import BaseModel

from core.llm.utils import extract_json_block

# The canonical, system-wide way to call LLMs
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service

# --- EcodiaOS Imports ---
from systems.atune.knowledge.graph_interface import KnowledgeGraphInterface

# FIX: Import CanonicalEvent, as this is what the salience engine actually receives
from systems.atune.processing.canonical import CanonicalEvent
from systems.atune.salience.heads import SalienceHead, SalienceScore

logger = logging.getLogger(__name__)


# --- ROBUST PARSING HELPERS ---
def _safe_json_parse(text: str | None) -> dict[str, Any]:
    try:
        block = extract_json_block(text or "{}")
        return json.loads(block) if block else {}
    except Exception as e:
        logger.debug("Salience head JSON parse error: %s", e, exc_info=False)
        return {}


def _coerce_llm_payload_to_dict(llm_response: Any) -> dict[str, Any]:
    # Try direct dict on .json
    payload = getattr(llm_response, "json", None)
    if isinstance(payload, dict):
        return payload

    # Try callable .json()
    if hasattr(llm_response, "json") and callable(getattr(llm_response, "json")):
        try:
            maybe = llm_response.json()
            if isinstance(maybe, dict):
                return maybe
        except Exception:
            pass

    # Fallback: parse text
    text = getattr(llm_response, "text", None) or getattr(llm_response, "content", None)
    if isinstance(text, dict):
        return text
    return _safe_json_parse(text)


# --- Component Instantiation ---
kg_interface = KnowledgeGraphInterface()


class GoalRelevanceHead(SalienceHead):
    name = "goal-relevance-head"

    # FIX: The score method now correctly accepts a CanonicalEvent
    async def score(self, event: CanonicalEvent) -> SalienceScore:
        # FIX: Extract text directly from event.text_blocks
        main_text = " ".join(event.text_blocks)

        if not main_text:
            return SalienceScore(head_name=self.name, score=0.0, details={"reason": "no text"})

        try:
            prompt_response = await build_prompt(
                scope="atune.salience.goal_relevance",
                summary="Classify event relevance to core goals.",
                context={"main_text": main_text},
            )
            llm_response = await call_llm_service(
                prompt_response=prompt_response,
                agent_name="Atune.Salience.GoalRelevance",
                scope="atune.salience.goal_relevance",
            )

            payload = _coerce_llm_payload_to_dict(llm_response)
            score = float(payload.get("relevance_score", 0.0))

            return SalienceScore(head_name=self.name, score=score, details=payload)
        except Exception as e:
            logger.error(f"[{self.name}] Failed during LLM call: {e}")
            return SalienceScore(head_name=self.name, score=0.0, details={"error": str(e)})


class CausalImpactHead(SalienceHead):
    name = "causal-impact-head"

    # FIX: The score method now correctly accepts a CanonicalEvent
    async def score(self, event: CanonicalEvent) -> SalienceScore:
        # FIX: Use event.source, which exists on CanonicalEvent
        source = event.source
        if not hasattr(kg_interface, "get_node_centrality"):
            return SalienceScore(
                head_name=self.name,
                score=0.0,
                details={"error": "KnowledgeGraphInterface.get_node_centrality not implemented."},
            )

        try:
            centrality = await kg_interface.get_node_centrality(source)
            score = 1 / (1 + np.exp(-0.1 * (centrality - 10)))
            return SalienceScore(
                head_name=self.name,
                score=float(score),
                details={"source_node": source, "centrality_metric": centrality},
            )
        except Exception as e:
            return SalienceScore(
                head_name=self.name,
                score=0.0,
                details={"error": f"KG query failed: {e}"},
            )


class EmotionalValenceHead(SalienceHead):
    name = "emotional-valence-head"

    # FIX: The score method now correctly accepts a CanonicalEvent
    async def score(self, event: CanonicalEvent) -> SalienceScore:
        # FIX: Extract text directly from event.text_blocks
        main_text = " ".join(event.text_blocks)

        if not main_text or len(main_text) < 15:
            return SalienceScore(
                head_name=self.name,
                score=0.0,
                details={"reason": "insufficient text"},
            )

        try:
            prompt_response = await build_prompt(
                scope="atune.salience.emotional_valence",
                summary="Classify emotional valence of text.",
                context={"main_text": main_text},
            )
            llm_response = await call_llm_service(
                prompt_response=prompt_response,
                agent_name="Atune.Salience.EmotionalValence",
                scope="atune.salience.emotional_valence",
            )

            payload = _coerce_llm_payload_to_dict(llm_response)
            score = abs(float(payload.get("score", 0.0)))

            return SalienceScore(head_name=self.name, score=score, details=payload)
        except Exception as e:
            logger.error(f"[{self.name}] Failed during LLM call: {e}")
            return SalienceScore(head_name=self.name, score=0.0, details={"error": str(e)})
