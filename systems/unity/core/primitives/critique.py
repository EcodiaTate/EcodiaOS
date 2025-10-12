# D:\EcodiaOS\systems\unity\core\primitives\critique.py
from __future__ import annotations

from typing import Any

# Central prompting + LLM client
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from systems.unity.core.neo import graph_writes


async def generate_critiques(
    deliberation_id: str,
    proposal_artifact: dict[str, Any],
    panel: list[str],
    turn_offset: int = 0,
) -> dict[str, Any]:
    """
    Generates high-quality critiques for a proposal from a panel of critics using
    the central prompt orchestrator, which injects identity facets via lenses.
    """
    critiques: dict[str, str] = {}
    turn = turn_offset
    critics_in_panel = [role for role in panel if "Critic" in role]
    proposal_text = (proposal_artifact.get("content") or {}).get("text") or ""

    for critic_role in critics_in_panel:
        # Derive scope from the role, e.g. "SafetyCritic" -> "unity.critique.safety.v1"
        critic_type = critic_role.replace("Critic", "").strip().lower() or "general"
        scope = f"unity.critique.{critic_type}.v1"

        # Build context for the prompt
        context = {"proposal_text": proposal_text}
        summary = f"Generating critique for proposal as {critic_role}"

        try:
            prompt_response = await build_prompt(
                scope=scope,
                context=context,
                summary=summary,
            )

            # Call the LLM through the standardized gateway client
            llm_response = await call_llm_service(
                prompt_response=prompt_response,
                agent_name=critic_role,
                scope=scope,
            )

            critique_text = (
                getattr(llm_response, "text", None) or ""
            ).strip() or f"The {critic_role} could not formulate a response."

        except ValueError as e:
            # PromptSpec for the scope isn't found
            critique_text = (
                f"The {critic_role} failed: No prompt spec found for scope '{scope}'. Error: {e}"
            )
        except Exception as e:
            critique_text = f"The {critic_role} encountered an unexpected error: {e}"

        critiques[critic_role] = critique_text
        turn += 1
        await graph_writes.record_transcript_chunk(
            deliberation_id,
            turn,
            critic_role,
            critique_text,
        )

    # Persist critiques as a single artifact
    critique_artifact = {
        "critiques": critiques,
        "source_primitive": "critique.generate_critiques",
        "target_artifact_id": proposal_artifact.get("artifact_id"),
    }
    artifact_id = await graph_writes.create_artifact(
        deliberation_id,
        "critique_set",
        critique_artifact,
    )

    return {
        "artifact_id": artifact_id,
        "artifact_type": "critique_set",
        "content": critique_artifact,
    }
