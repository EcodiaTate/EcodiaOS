from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from core.utils.neo.cypher_query import cypher_query
from systems.equor.schemas import Attestation  # <-- Pydantic model

attest_router = APIRouter()
logger = logging.getLogger(__name__)


@attest_router.post("/attest")
async def receive_attestation(
    attestation: Attestation,
) -> dict[str, Any]:
    """
    Receive a governance attestation and persist it.
    - Accepts a JSON body matching systems.equor.schemas.Attestation
    - Writes only primitive properties / arrays (no nested maps!)
    - Links to Episode if present
    """
    try:
        # Minimal validation / normalization
        run_id = attestation.run_id
        episode_id = attestation.episode_id
        agent = attestation.agent
        patch_id = attestation.applied_prompt_patch_id
        breaches = list(attestation.breaches or [])
        now_iso = datetime.now(UTC).isoformat()

        # Persist with primitives only
        params = {
            "run_id": run_id,
            "episode_id": episode_id,
            "agent": agent,
            "patch_id": patch_id,
            "breaches": breaches,
            "now": now_iso,
        }

        # NOTE: Fixes Neo4j deprecation: explicit variable scope clause for subquery.
        query = """
        MERGE (a:Attestation {id: $run_id})
        ON CREATE SET a.created_at = datetime($now)
        SET
          a.agent = $agent,
          a.applied_prompt_patch_id = $patch_id,
          a.breaches = $breaches,
          a.last_seen = datetime($now)

        WITH a
        CALL (a) {
          WITH a, $episode_id AS eid
          WHERE eid IS NOT NULL AND eid <> ''
          MERGE (e:Episode {id: eid})
          ON CREATE SET e.created_at = datetime($now)
          SET e.last_seen = datetime($now)
          MERGE (e)-[:ATTESTED_BY]->(a)
          RETURN 1 AS _
        }
        RETURN a.id AS run_id
        """

        await cypher_query(query, params=params)
        return {
            "ok": True,
            "run_id": run_id,
            "episode_id": episode_id,
            "persisted": True,
            "breaches": breaches,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to persist attestation run_id=%s",
            getattr(attestation, "run_id", "<none>"),
        )
        raise HTTPException(status_code=500, detail=f"Could not persist attestation: {e}")
