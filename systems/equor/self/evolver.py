# systems/equor/core/self/evolver.py
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, List

from pydantic import ValidationError

from core.llm.bus import event_bus
from core.llm.utils import extract_json_block

# EcodiaOS Core Imports
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from core.utils.neo.cypher_query import cypher_query
from systems.equor.core.identity.registry import IdentityRegistry
from systems.equor.core.neo import graph_writes
from systems.equor.schemas import (
    AtuneIdentityReflectionRequest,
    EcodiaCoreIdentity,
    Facet,
    UnityDeliberationCompleteEvent,
)

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Equor.Evolver")

# Agent scopes for each reflection tier, allowing for different prompts
DEEP_REFLECTION_SCOPE = "equor.identity.deliberation.v1"
DIRECT_REFLECTION_SCOPE = "equor.identity.direct_reflection.v1"
CORE_SYNTHESIS_SCOPE = "equor.system_self.synthesis.v1"
AGENT_NAME = "Equor.Evolver"

# The core identity of the system itself, not a specific sub-agent
ECODIA_SYSTEM_AGENT_ID = os.getenv("IDENTITY_AGENT") or "EcodiaOS.System"

# The two topics this service now listens to
UNITY_TOPIC = "unity.deliberation.complete"
ATUNE_TOPIC = "atune.identity_reflection.requested"


class IdentityEvolver:
    """
    Listens to high-salience events from across the system and proposes the
    creation or versioning of core identity Facets. This forms the learning
    and evolution loop for the system's sense of self, operating in two tiers.
    """

    def __init__(self):
        self.registry = IdentityRegistry()

    async def _get_current_identity_context(self) -> list[dict[str, Any]]:
        """
        Fetches the current active facets for the core system to provide
        the LLM with the necessary context for reflection.
        """
        try:
            _, facets, _ = await self.registry.get_active_components_for_profile(
                agent=ECODIA_SYSTEM_AGENT_ID,
                profile_name="default",
            )
            return [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "category": f.get("category"),
                    "text": f.get("text"),
                }
                for f in facets
            ]
        except Exception as e:
            logger.warning(f"[Evolver] Could not fetch current identity context: {e}")
            return []

    async def process_deliberation_event(self, event: dict[str, Any]) -> None:
        """
        TIER 3: Processes a completed deliberation from Unity for deep reflection.
        """
        try:
            deliberation = UnityDeliberationCompleteEvent(**event)
            logger.info(
                f"[Evolver-T3] Processing deliberation event, "
                f"episode_id={deliberation.deliberation_episode_id}",
            )
        except ValidationError as e:
            logger.error(
                "[Evolver-T3] Event failed validation for UnityDeliberationCompleteEvent schema: %s",
                e,
            )
            return

        is_core_synthesis_event = (
            deliberation.conclusion.confidence >= 0.9
            and deliberation.conclusion.agreement_level >= 0.9
        )

        if is_core_synthesis_event:
            logger.info(
                "🔥 Core Identity Synthesis triggered by deliberation %s",
                deliberation.deliberation_episode_id,
            )
            current_core_identity = await self._get_current_core_identity()
            context = {
                "deliberation": deliberation.model_dump(),
                "current_core_identity": current_core_identity,
            }
            summary = (
                "Synthesize a new version of the EcodiaOS core identity based on a "
                "profound system-wide deliberation."
            )
            await self._synthesize_new_core(
                context,
                summary,
                deliberation.deliberation_episode_id,
            )
        else:
            logger.info(
                "Standard facet reflection triggered for deliberation %s",
                deliberation.deliberation_episode_id,
            )
            current_facets = await self._get_current_identity_context()
            context = {
                "topic": deliberation.topic,
                "conclusion": deliberation.conclusion.text,
                "participating_agents": deliberation.participating_agents,
                "triggering_source": deliberation.triggering_source,
                "current_facets": current_facets,
            }
            summary = "Reflect on a full system deliberation to potentially evolve identity."
            await self._reflect_and_propose(
                DEEP_REFLECTION_SCOPE,
                context,
                summary,
                deliberation.deliberation_episode_id,
            )

    async def process_reflection_request(self, event: dict[str, Any]) -> None:
        """
        TIER 2: Processes a direct reflection request from Atune.
        """
        try:
            request = AtuneIdentityReflectionRequest(**event)
            logger.info(
                "[Evolver-T2] Processing direct reflection request, decision_id=%s",
                request.decision_id,
            )
        except ValidationError as e:
            logger.error(
                "[Evolver-T2] Event failed validation for AtuneIdentityReflectionRequest schema: %s",
                e,
            )
            return

        current_facets = await self._get_current_identity_context()
        context = {
            "triggering_event_text": " ".join(request.triggering_event.text_blocks),
            "salience_scores": request.salience_scores,
            "current_facets": current_facets,
        }
        summary = "Reflect on a single identity-relevant event to potentially evolve identity."
        await self._reflect_and_propose(
            DIRECT_REFLECTION_SCOPE,
            context,
            summary,
            request.decision_id,
        )

    async def _get_current_core_identity(self) -> dict[str, Any] | None:
        """Fetches the latest version of the EcodiaCoreIdentity."""
        query = """
            MATCH (core:EcodiaCoreIdentity)
            WHERE NOT (core)-[:SUPERSEDED_BY]->()
            RETURN core
            ORDER BY core.version DESC
            LIMIT 1
        """
        try:
            result = await cypher_query(query)
            return result[0]["core"] if result else None
        except Exception as e:
            logger.error(f"[Evolver] Critical error fetching core identity: {e}")
            return None

    async def _synthesize_new_core(
        self,
        context: dict[str, Any],
        summary: str,
        trace_id: str,
    ):
        """
        Runs the LLM to synthesize a new EcodiaCoreIdentity and persists it.
        """
        try:
            prompt_response = await build_prompt(
                scope=CORE_SYNTHESIS_SCOPE,
                context=context,
                summary=summary,
            )
            llm_response = await call_llm_service(
                prompt_response=prompt_response,
                agent_name=AGENT_NAME,
                scope=CORE_SYNTHESIS_SCOPE,
            )

            proposal = getattr(llm_response, "json", None)
            if not isinstance(proposal, dict):
                text = getattr(llm_response, "text", "") or ""
                block = extract_json_block(text) or "{}"
                import json as _json

                proposal = _json.loads(block)
        except Exception as e:
            logger.error(
                f"[Evolver-Core] LLM call failed for trace_id {trace_id}: {e}",
                exc_info=True,
            )
            return

        if not isinstance(proposal, dict) or not proposal.get(
            "should_update_core_identity",
        ):
            logger.info(
                "[Evolver-Core] LLM determined no core identity update is needed for trace_id %s.",
                trace_id,
            )
            return

        core_def = proposal.get("core_identity_definition")
        if not isinstance(core_def, dict):
            logger.error(
                "[Evolver-Core] LLM proposed a core update but the definition was invalid for trace_id %s",
                trace_id,
            )
            return

        try:
            current_version = (context.get("current_core_identity") or {}).get(
                "version",
                0,
            )
            current_id = (context.get("current_core_identity") or {}).get("id")

            new_core = EcodiaCoreIdentity(
                id=f"ecodia-core-{uuid.uuid4().hex}",
                version=current_version + 1,
                supersedes=current_id,
                synthesis_trace_id=trace_id,
                **core_def,  # narrative_summary, core_directives, etc.
            )

            new_id = await graph_writes.upsert_core_identity(new_core)
            logger.info(
                "✅✅✅ [Evolver-Core] Successfully CREATED new Core Identity Version %s "
                "(ID: %s), superseding %s.",
                new_core.version,
                new_id,
                current_id,
            )

        except ValidationError as e:
            logger.error(
                "🚨 [Evolver-Core] LLM output failed Pydantic validation for EcodiaCoreIdentity "
                "on trace_id %s: %s",
                trace_id,
                e,
            )
        except Exception as e:
            logger.error(
                "🚨 [Evolver-Core] Failed to write new Core Identity to graph for trace_id %s: %s",
                trace_id,
                e,
                exc_info=True,
            )

    async def _reflect_and_propose(
        self,
        scope: str,
        context: dict[str, Any],
        summary: str,
        trace_id: str,
    ):
        """
        Generic helper to run the LLM reflection and persist a new Facet.
        """
        try:
            prompt_response = await build_prompt(
                scope=scope,
                context=context,
                summary=summary,
            )
            llm_response = await call_llm_service(
                prompt_response=prompt_response,
                agent_name=AGENT_NAME,
                scope=scope,
            )

            proposal = getattr(llm_response, "json", None)
            if not isinstance(proposal, dict):
                import json as _json

                text = getattr(llm_response, "text", "") or ""
                block = extract_json_block(text) or "{}"
                proposal = _json.loads(block)
        except Exception as e:
            logger.error(
                f"[Evolver] LLM call failed for trace_id {trace_id}: {e}",
                exc_info=True,
            )
            return

        if not isinstance(proposal, dict) or not proposal.get("should_create_facet"):
            logger.info(
                "[Evolver] LLM determined no new facet is needed for trace_id %s.",
                trace_id,
            )
            return

        facet_definition = proposal.get("facet_definition")
        if not isinstance(facet_definition, dict):
            logger.error(
                "[Evolver] LLM proposed a facet but the definition was invalid for trace_id %s",
                trace_id,
            )
            return

        try:
            new_facet = Facet(**facet_definition)
            facet_id = await graph_writes.upsert_facet(new_facet)

            if new_facet.supersedes:
                logger.info(
                    "✅ [Evolver] Successfully CREATED new version for Facet '%s' "
                    "(ID: %s), superseding %s.",
                    new_facet.name,
                    facet_id,
                    new_facet.supersedes,
                )
            else:
                logger.info(
                    "✅ [Evolver] Successfully CREATED new identity Facet '%s' (ID: %s).",
                    new_facet.name,
                    facet_id,
                )

        except ValidationError as e:
            logger.error(
                "🚨 [Evolver] LLM output failed Pydantic validation for Facet schema "
                "on trace_id %s: %s",
                trace_id,
                e,
            )
        except Exception as e:
            logger.error(
                "🚨 [Evolver] Failed to write new Facet to graph for trace_id %s: %s",
                trace_id,
                e,
                exc_info=True,
            )


async def run_evolver_service():
    """
    Initializes and runs the IdentityEvolver service, subscribing it to both
    the deep and direct reflection event topics.
    """
    evolver = IdentityEvolver()
    logger.info("🚀 [Evolver Service] Starting and subscribing to topics...")

    # Subscribe to both Tier 3 (deep) and Tier 2 (direct) reflection events
    unsub_unity = event_bus.subscribe(UNITY_TOPIC, evolver.process_deliberation_event)
    unsub_atune = event_bus.subscribe(ATUNE_TOPIC, evolver.process_reflection_request)
    logger.info("  - Subscribed to '%s' for deep reflection.", UNITY_TOPIC)
    logger.info("  - Subscribed to '%s' for direct reflection.", ATUNE_TOPIC)

    try:
        await asyncio.Future()  # Keep the service alive indefinitely
    finally:
        logger.info("🔌 [Evolver Service] Shutting down and unsubscribing...")
        unsub_unity()
        unsub_atune()


# --- Test Runner for Standalone Execution ---
async def _publish_mock_events():
    """Publishes mock events for both tiers to test the service."""
    await asyncio.sleep(2)
    logger.info("[Mock Publisher] Starting to publish mock events...")

    # Mock Tier 3 Event from Unity
    mock_unity_event = {
        "deliberation_episode_id": "unity_ep_mock_67890",
        "triggering_event_id": "ep_mock_12345",
        "triggering_source": "EcodiaOS.Voxis",
        "topic": "Reflection on long-term ecological responsibility",
        "participating_agents": ["Evo", "Ethor", "Simula"],
        "conclusion": {
            "text": "The system concludes that a principle of intergenerational ecological stewardship is a core ethical imperative...",
            "confidence": 0.95,
            "agreement_level": 0.9,
        },
    }
    await event_bus.publish(UNITY_TOPIC, mock_unity_event)
    logger.info("[Mock Publisher] Published Tier 3 event to '%s'.", UNITY_TOPIC)

    await asyncio.sleep(1)

    # Mock Tier 2 Event from Atune
    mock_atune_event = {
        "decision_id": "atune_dec_mock_abcde",
        "triggering_event": {
            "event_id": "ev_mock_9876",
            "source": "rss_ingestor",
            "event_type": "article.processed",
            "text_blocks": [
                "A new study on mycelial networks demonstrates their critical role in forest carbon sequestration...",
            ],
            "numerical_features": {},
            "text_hash": "somehash",
            "original_event": {},
        },
        "salience_scores": {"identity-relevance-head": {"final_score": 0.88}},
    }
    await event_bus.publish(ATUNE_TOPIC, mock_atune_event)
    logger.info("[Mock Publisher] Published Tier 2 event to '%s'.", ATUNE_TOPIC)


if __name__ == "__main__":

    async def main():
        print("--- Running Identity Evolver in standalone test mode ---")
        print(
            f"--- Listening for events on TWO topics: '{UNITY_TOPIC}' and '{ATUNE_TOPIC}' ---",
        )
        print(
            "--- Mock events for both tiers will be published shortly. Press Ctrl+C to exit. ---",
        )

        service_task = asyncio.create_task(run_evolver_service())
        mock_task = asyncio.create_task(_publish_mock_events())
        await asyncio.gather(service_task, mock_task)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n--- [Evolver Service] Shutdown requested by user. ---")
