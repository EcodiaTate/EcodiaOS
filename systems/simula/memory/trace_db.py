# systems/simula/memory/trace_db.py

from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

from core.utils.neo.cypher_query import cypher_query

from .schemas import SynapticTrace

log = logging.getLogger(__name__)


class TraceDBClient:
    """
    [PRODUCTION IMPLEMENTATION]
    Manages the persistent storage and retrieval of Synaptic Traces in Neo4j.
    This client uses the graph database for both property storage and
    high-speed vector similarity search, forming the MDO's long-term memory.
    """

    async def save(self, trace: SynapticTrace):
        """
        Saves a new trace to the Neo4j graph. It uses MERGE to ensure that
        if a trace with the same ID is saved again, it's updated rather than duplicated.
        """
        log.info(f"[TraceDB-Neo4j] Persisting trace: {trace.trace_id}")

        # We store complex objects like action_sequence as JSON strings in the graph.
        props_to_set = trace.model_dump(exclude={"triggering_state_vector"})
        props_to_set["action_sequence_json"] = json.dumps(trace.action_sequence)
        del props_to_set["action_sequence"]

        query = """
        MERGE (t:SynapticTrace {trace_id: $trace_id})
        SET t += $props, t.triggering_state_vector = $vector
        """

        params = {
            "trace_id": trace.trace_id,
            "props": props_to_set,
            "vector": trace.triggering_state_vector,
        }

        await cypher_query(query, params)

    async def search(
        self,
        query_vector: list[float],
        min_confidence: float,
        similarity_threshold: float,
        top_k: int = 1,
    ) -> SynapticTrace | None:
        """
        Performs a high-speed vector similarity search using the Neo4j index.
        It finds the single best matching trace that meets our confidence and
        similarity thresholds.
        """
        if not query_vector:
            return None

        query = """
        CALL db.index.vector.queryNodes('synaptic_trace_trigger_vectors', $top_k, $vector)
        YIELD node AS trace, score
        WHERE score >= $similarity_threshold AND trace.confidence_score >= $min_confidence
        RETURN trace, score
        ORDER BY score DESC
        LIMIT 1
        """

        params = {
            "top_k": top_k,
            "vector": query_vector,
            "similarity_threshold": similarity_threshold,
            "min_confidence": min_confidence,
        }

        result = await cypher_query(query, params)

        if not result:
            return None

        node_data = result[0]["trace"]
        score = result[0]["score"]

        log.info(
            f"[TraceDB-Neo4j] Found matching trace {node_data.get('trace_id')} with similarity {score:.4f}"
        )

        # Reconstruct the Pydantic model from the raw graph data.
        action_sequence = json.loads(node_data.get("action_sequence_json", "[]"))

        return SynapticTrace(
            trace_id=node_data["trace_id"],
            triggering_state_vector=node_data["triggering_state_vector"],
            action_sequence=action_sequence,
            outcome_utility=node_data["outcome_utility"],
            confidence_score=node_data["confidence_score"],
            generation_timestamp=node_data["generation_timestamp"],
            last_applied_timestamp=node_data.get("last_applied_timestamp"),
            application_count=node_data.get("application_count", 0),
        )

    async def record_application(self, trace_id: str):
        """Updates metadata for a trace in the graph when it is used."""
        query = """
        MATCH (t:SynapticTrace {trace_id: $trace_id})
        SET t.application_count = coalesce(t.application_count, 0) + 1,
            t.last_applied_timestamp = $timestamp
        """
        params = {"trace_id": trace_id, "timestamp": time.time()}
        await cypher_query(query, params)
        log.debug(f"[TraceDB-Neo4j] Updated application metadata for trace {trace_id}")
