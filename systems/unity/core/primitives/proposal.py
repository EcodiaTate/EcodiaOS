# D:\EcodiaOS\systems\unity\core\primitives\proposal.py
from __future__ import annotations

from typing import Any

# Central prompting system
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from systems.unity.core.neo import graph_writes
from systems.unity.schemas import DeliberationSpec


async def generate_proposal(
    spec: DeliberationSpec,
    deliberation_id: str,
    turn_offset: int = 0,
) -> dict[str, Any]:
    """
    Generates a high-quality initial proposal using the central prompt orchestrator,
    injecting mission, style, and voice facets via lenses.
    """
    scope = "unity.proposal.generate.v1"

    # Full deliberation spec as context; prompt extracts topic, goal, inputs, etc.
    context = {"deliberation_spec": spec.model_dump()}
    summary = f"Generating initial proposal for topic: {spec.topic}"

    try:
        prompt_response = await build_prompt(
            scope=scope,
            context=context,
            summary=summary,
        )

        # Call the LLM via standardized gateway
        llm_response = await call_llm_service(
            prompt_response=prompt_response,
            agent_name="Unity.Proposer",
            scope=scope,
        )
        proposal_text = (
            getattr(llm_response, "text", None) or "The model failed to generate a proposal."
        )

    except ValueError as e:
        proposal_text = f"The Proposer failed: No prompt spec found for scope '{scope}'. Error: {e}"
    except Exception as e:
        proposal_text = f"The Proposer encountered an unexpected error: {e}"

    # Persist proposal draft artifact
    proposal_artifact = {
        "text": proposal_text,
        "source_primitive": "proposal.generate_proposal",
    }
    artifact_id = await graph_writes.create_artifact(
        deliberation_id,
        "proposal_draft",
        proposal_artifact,
    )

    await graph_writes.record_transcript_chunk(
        deliberation_id,
        turn=turn_offset + 1,
        role="Proposer",
        content=proposal_text,
    )

    return {
        "artifact_id": artifact_id,
        "artifact_type": "proposal_draft",
        "content": proposal_artifact,
    }
