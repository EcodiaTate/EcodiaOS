from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

# Make sure to import the centralized helper
from core.utils.neo.cypher_query import cypher_query
from systems.equor.core.identity.composer import CompositionError, PromptComposer
from systems.equor.core.neo import graph_writes
from systems.equor.schemas import ComposeRequest, ComposeResponse
from systems.synapse.core.snapshots import stamp as rcu_stamp

# =======================================================================
# == Service Class for Core Logic
# =======================================================================


class CompositionService:
    """Encapsulates the business logic for composing a prompt patch."""

    def __init__(self, composer: PromptComposer):
        self.composer = composer

    # inside CompositionService
    def _derive_intent(self, req: ComposeRequest) -> str:
        # try top-level optional fields if they exist
        intent = getattr(req, "intent", None) or getattr(req, "task_key", None)
        if intent:
            return str(intent)

        # try context (dict or pydantic model)
        ctx = getattr(req, "context", None)
        if isinstance(ctx, dict):
            for k in ("intent", "task_key", "request_path", "path"):
                v = ctx.get(k)
                if v:
                    return str(v)

        # last-ditch: use agent if present, else a static default
        agent = getattr(req, "agent", None)
        return f"{agent}.compose" if agent else "equor.compose"

    async def handle_composition(self, req: ComposeRequest) -> ComposeResponse:
        """
        Orchestrates the full process of composing and persisting a prompt patch.
        1. Guarantees an Episode exists.
        2. Creates and links an RCU snapshot.
        3. Composes the prompt patch.
        4. Persists the final artifact to the graph.
        """
        # Step 1 & 2: Ensure Episode and RCU Snapshot are persisted and linked.
        episode_id = await self._ensure_episode(req)
        rcu_ref = await self._create_and_link_rcu_snapshot(episode_id)

        # Step 3: Create a validated request model with the definite episode_id.
        # Using model_copy is cleaner than dict conversion.
        req_with_episode = req.model_copy(update={"episode_id": episode_id})

        # Step 4: Delegate to the core composer.
        response = await self.composer.compose(req_with_episode, rcu_ref=rcu_ref)

        if not response.prompt_patch_id or not response.text:
            raise CompositionError("Composer returned an empty or invalid patch.")

        # Step 5: Persist the generated artifact.
        await graph_writes.save_prompt_patch(response, req_with_episode)

        return response

    async def _ensure_episode(self, req: ComposeRequest) -> str:
        episode_id = getattr(req, "episode_id", None) or f"ep_{uuid.uuid4().hex}"
        intent = self._derive_intent(req)
        now_iso = datetime.now(UTC).isoformat()

        await cypher_query(
            """
            MERGE (e:Episode {id:$id})
            ON CREATE SET
            e.created_at = datetime($now),
            e.source     = 'equor.compose',
            e.intent     = $intent
            ON MATCH SET
            e.last_seen  = datetime($now)
            """,
            {"id": episode_id, "now": now_iso, "intent": intent},
        )
        return episode_id

    async def _create_and_link_rcu_snapshot(self, episode_id: str) -> str:
        """Creates a deterministic RCU snapshot and links it to the episode."""
        snapshot = rcu_stamp()
        snap_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        rcu_ref = "rcu_" + hashlib.sha256(snap_json.encode("utf-8")).hexdigest()[:24]
        now_iso = datetime.now(UTC).isoformat()

        await cypher_query(
            """
            MERGE (s:RCUSnapshot {id:$sid})
            ON CREATE SET s.body = $body, s.created_at = datetime($now)
            WITH s
            MATCH (e:Episode {id:$eid})
            MERGE (e)-[:HAS_SNAPSHOT]->(s)
            """,
            {"sid": rcu_ref, "body": snap_json, "now": now_iso, "eid": episode_id},
        )
        return rcu_ref


# =======================================================================
# == FastAPI Dependencies & Router
# =======================================================================

compose_router = APIRouter()
logger = logging.getLogger(__name__)


# Dependency Providers
async def get_composer() -> PromptComposer:
    """Provides a PromptComposer instance."""
    return PromptComposer()


async def get_composition_service(
    composer: PromptComposer = Depends(get_composer),
) -> CompositionService:
    """Provides the main CompositionService, injecting its dependencies."""
    return CompositionService(composer)


# =======================================================================
# == API Endpoint
# =======================================================================


@compose_router.post("/compose", response_model=ComposeResponse)
async def compose_prompt_patch(
    req: ComposeRequest,
    service: CompositionService = Depends(get_composition_service),
):
    """
    Composes a deterministic prompt patch by orchestrating identity,
    context, and snapshotting.
    """
    try:
        # Example of how you would use the resolver if you were calling another service:
        # target_endpoint = resolve_endpoint("SOME_SERVICE_KEY", "/some/fallback/path")
        # await http_client.post(target_endpoint, ...)

        return await service.handle_composition(req)
    except CompositionError as e:
        logger.warning("CompositionError in /equor/compose: %s", e)
        raise HTTPException(status_code=422, detail=f"Could not process composition: {e}") from e
    except HTTPException:
        # Re-raise known HTTP exceptions without modification.
        raise
    except Exception as e:
        logger.exception("Unhandled error in /equor/compose")
        raise HTTPException(
            status_code=500, detail=f"An internal server error occurred: {e}"
        ) from e
