# systems/voxis/tools/drivers/memory_driver.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, ValidationError

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query
from systems.axon.mesh.registry import DriverInterface
from systems.voxis.core.user_profile import (
    SOULINPUT_INDEX_CANDIDATES,
    SOULRESPONSE_INDEX_CANDIDATES,
    _clip_messages,
    _first_working_vector_query,
)

log = logging.getLogger("MemoryDriver")

# --- Pydantic Schemas for Validation ---


class SearchArgs(BaseModel):
    query: str = Field(..., description="The natural language query to search for in memory.")
    user_id: str = Field(..., description="The UUID of the user whose memory is being searched.")
    limit: int = Field(5, ge=1, le=20, description="Maximum number of memory snippets to return.")


class _Spec(BaseModel):
    driver_name: str
    version: str
    supported_actions: list[str]
    summary: str


# --- Driver Implementation ---


class MemoryDriver(DriverInterface):
    """
    A driver for introspective memory access, allowing the agent to perform
    semantic searches over a specific user's conversational history.
    """

    NAME: str = "memory"
    VERSION: str = "1.0.0"

    ACTION_SEARCH: Literal["semantic_search"] = "semantic_search"

    def describe(self) -> _Spec:
        """Returns structured metadata about the driver's capabilities."""
        return _Spec(
            driver_name=self.NAME,
            version=self.VERSION,
            supported_actions=[self.ACTION_SEARCH],
            summary="Searches and retrieves relevant snippets from a user's long-term conversational memory.",
        )

    async def semantic_search(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Performs a semantic search over the user's conversational history.
        """
        try:
            args = SearchArgs(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        memories: list[dict[str, str]] = []
        try:
            embed = await get_embedding(args.query, task_type="RETRIEVAL_QUERY")

            # Query user's past inputs
            input_hits = await _first_working_vector_query(
                SOULINPUT_INDEX_CANDIDATES, k=args.limit, vec=embed
            )
            input_ids = [r.get("id") for r in (input_hits or []) if r.get("id")]

            # Query user's past responses
            resp_hits = await _first_working_vector_query(
                SOULRESPONSE_INDEX_CANDIDATES, k=args.limit, vec=embed
            )
            resp_ids = [r.get("id") for r in (resp_hits or []) if r.get("id")]

            # Retrieve and pair the conversations for context
            pairing_q = """
            UNWIND $inputIds AS iid
            MATCH (si:SoulInput) WHERE elementId(si) = iid AND si.user_id = $userId
            OPTIONAL MATCH (si)-[:GENERATES]->(sir:SoulResponse)
            RETURN elementId(si) AS id, si.text AS user_content, sir.text AS assistant_content,
                   coalesce(si.timestamp, datetime({epochMillis:0})) AS ts
            UNION ALL
            UNWIND $respIds AS rid
            MATCH (sr:SoulResponse) WHERE elementId(sr) = rid AND sr.user_id = $userId
            OPTIONAL MATCH (si2:SoulInput)-[:GENERATES]->(sr)
            RETURN elementId(sr) AS id, si2.text AS user_content, sr.text AS assistant_content,
                   coalesce(sr.timestamp, datetime({epochMillis:0})) AS ts
            ORDER BY ts DESC
            """
            pair_rows = await cypher_query(
                pairing_q,
                {"inputIds": input_ids, "respIds": resp_ids, "userId": args.user_id},
            )

            seen = set()
            for pr in pair_rows or []:
                uid = pr.get("id")
                if uid in seen:
                    continue
                seen.add(uid)
                u = (pr.get("user_content") or "").strip()
                a = (pr.get("assistant_content") or "").strip()

                if u and a:
                    memories.append(
                        {"role": "context", "content": f"User said: '{u}'\nI responded: '{a}'"}
                    )
                elif u:
                    memories.append({"role": "user", "content": u})

            return {"status": "ok", "memories": _clip_messages(memories, hard_limit=args.limit)}
        except Exception as e:
            log.exception(f"Memory search failed for user {args.user_id} with query '{args.query}'")
            return {
                "status": "error",
                "message": f"An internal error occurred during memory search: {e}",
            }

    def repro_bundle(self) -> dict[str, Any]:
        """Returns a dictionary of non-sensitive configuration for reproducibility."""
        return {
            "driver_name": self.NAME,
            "version": self.VERSION,
            "input_indices": SOULINPUT_INDEX_CANDIDATES,
            "response_indices": SOULRESPONSE_INDEX_CANDIDATES,
        }

    async def self_test(self) -> dict[str, Any]:
        """Performs a quick, non-destructive health check."""
        try:
            # Check if at least one vector index exists
            indices_info = await cypher_query("SHOW VECTOR INDEXES")
            index_names = {info.get("name") for info in (indices_info or [])}

            if not (set(SOULINPUT_INDEX_CANDIDATES) & index_names):
                raise RuntimeError(
                    f"Required vector index for SoulInput not found. Searched for: {SOULINPUT_INDEX_CANDIDATES}"
                )

            return {
                "status": "ok",
                "message": "Memory driver appears healthy and vector indexes are available.",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
