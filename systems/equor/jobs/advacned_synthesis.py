# systems/equor/jobs/advanced_synthesis.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)

# --- Strategy 1: Thematic Clustering (Good for general interests) ---

THEMATIC_CLUSTERING_Q = """
MATCH (seed:SoulInput {user_id: $uid})
WHERE seed.embedding IS NOT NULL
WITH seed ORDER BY seed.timestamp DESC LIMIT 1
CALL db.index.vector.queryNodes('soulinput-gemini-3072', $limit, seed.embedding) YIELD node AS si
WHERE si.user_id = $uid
OPTIONAL MATCH (si)-[:GENERATES]->(sr:SoulResponse)
RETURN si.text AS user_text, sr.text AS assistant_text
ORDER BY si.timestamp DESC
"""


async def gather_thematic_cluster(user_id: str, limit: int) -> list[dict[str, str]]:
    """Gathers conversation pairs semantically related to the user's latest topic."""
    logger.info(f"[{user_id}] Gathering with 'thematic_cluster' strategy...")
    rows = await cypher_query(THEMATIC_CLUSTERING_Q, {"uid": user_id, "limit": limit})
    return [
        {"user": r.get("user_text", ""), "assistant": r.get("assistant_text", "")} for r in rows
    ]


# --- Strategy 2: "Self-Reflection" Probes (Good for explicit facts) ---

SELF_REFLECTION_PROBE_Q = """
CALL db.index.vector.queryNodes('soulinput-gemini-3072', $limit, $probe_vec) YIELD node AS si
WHERE si.user_id = $uid
OPTIONAL MATCH (si)-[:GENERATES]->(sr:SoulResponse)
RETURN si.text AS user_text, sr.text AS assistant_text
ORDER BY si.timestamp DESC
"""


async def gather_self_reflection_probes(user_id: str, limit: int) -> list[dict[str, str]]:
    """Finds conversation turns where the user is likely talking about themselves."""
    logger.info(f"[{user_id}] Gathering with 'self_reflection' strategy...")
    probe_text = "My personal opinion is that I am a person who believes in and feels that..."
    probe_vec = await get_embedding(probe_text, task_type="RETRIEVAL_QUERY")
    rows = await cypher_query(
        SELF_REFLECTION_PROBE_Q, {"uid": user_id, "limit": limit, "probe_vec": probe_vec}
    )
    return [
        {"user": r.get("user_text", ""), "assistant": r.get("assistant_text", "")} for r in rows
    ]


# --- Strategy 3: "Curiosity Probes" (Good for intellectual fingerprint) ---

CURIOSITY_PROBE_Q = """
// Find a sample of questions the user has asked
MATCH (si:SoulInput {user_id: $uid})
WHERE si.text ENDS WITH '?' AND si.embedding IS NOT NULL
WITH si, rand() AS r
ORDER BY r
LIMIT 10
// Average their embeddings to find the user's "center of curiosity"
WITH avg(si.embedding) AS curiosity_vec

// Use that average vector to find semantically similar conversation turns
CALL db.index.vector.queryNodes('soulinput-gemini-3072', $limit, curiosity_vec) YIELD node AS similar_input
WHERE similar_input.user_id = $uid
OPTIONAL MATCH (similar_input)-[:GENERATES]->(sr:SoulResponse)
RETURN similar_input.text AS user_text, sr.text AS assistant_text
ORDER BY similar_input.timestamp DESC
"""


async def gather_curiosity_probes(user_id: str, limit: int) -> list[dict[str, str]]:
    """Analyzes a user's questions to find and cluster their core areas of curiosity."""
    logger.info(f"[{user_id}] Gathering with 'curiosity_probes' strategy...")
    rows = await cypher_query(CURIOSITY_PROBE_Q, {"uid": user_id, "limit": limit})
    return [
        {"user": r.get("user_text", ""), "assistant": r.get("assistant_text", "")} for r in rows
    ]


# --- Strategy Runner ---

STRATEGY_MAP = {
    "thematic_cluster": gather_thematic_cluster,
    "self_reflection": gather_self_reflection_probes,
    "curiosity_probes": gather_curiosity_probes,
}


async def gather_samples_with_strategy(
    strategy: str,
    user_id: str,
    limit: int,
) -> list[dict[str, str]]:
    """Selects and executes a gathering strategy to get conversation samples."""
    gather_function = STRATEGY_MAP.get(strategy)
    if not gather_function:
        logger.warning(
            f"Unknown synthesis strategy '{strategy}'. Falling back to 'thematic_cluster'."
        )
        gather_function = gather_thematic_cluster

    return await gather_function(user_id, limit)
