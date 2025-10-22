# systems/thread/core/narrative.py
#
# REFACTORED: MODERN NARRATIVE ENGINE (FKA IDENTITY SHIFT EVALUATOR)
# This service is the definitive "Thread" system. Its sole responsibility is to
# listen for completed conversational turns and stitch them into a coherent,
# chronological, and causal narrative graph in Neo4j. It no longer handles
# identity, which is now the domain of the Equor system.
#
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

# EcodiaOS Core Imports
from core.utils.time import now, now_iso

# Safe, low-level graph and embedding access.
# We define graph logic here as it is Thread's core domain.
try:
    from core.utils.neo.cypher_query import cypher_query
except Exception:
    cypher_query = None  # type: ignore

try:
    from core.llm.embeddings_gemini import get_embedding
except Exception:
    get_embedding = None  # type: ignore

# --------------------------------------------------------------------------
# Logger & Constants
# --------------------------------------------------------------------------
logger = logging.getLogger("ecodia.thread")
EXPECTED_DIMS = 3072  # System-wide standard for document embeddings

# --------------------------------------------------------------------------
# 🦾 Core Narrative Graph Utilities
# --------------------------------------------------------------------------


async def _embed_text_3072(text: str) -> list[float] | None:
    """
    Embeds text with a hard expectation of 3072 dimensions for consistency.
    This function is robust and will not raise exceptions, returning None on failure.
    """
    if not text or not text.strip() or get_embedding is None:
        logger.warning("[Thread:Embed] Skipping embedding; text is empty or embedder unavailable.")
        return None

    try:
        # Use RETRIEVAL_DOCUMENT for storing searchable memories
        vec = await get_embedding(text, task_type="RETRIEVAL_DOCUMENT", dimensions=EXPECTED_DIMS)
        if isinstance(vec, list) and len(vec) == EXPECTED_DIMS:
            return vec
        logger.error(
            f"[Thread:Embed] Failed to get 3072D vector; got len={len(vec) if vec else 'None'}.",
        )
    except Exception as e:
        logger.error(f"[Thread:Embed] Embedding call failed: {e}", exc_info=True)

    return None


async def ingest_turn_node(
    role: str,
    user_id: str,
    session_id: str,
    text: str,
    episode_id: str | None = None,
) -> str | None:
    """
    Creates a single, embeddable node in the graph representing one
    part of a conversation, applying both new and legacy labels for
    full backward compatibility.

    Returns:
        The UUID of the newly created node, or None on failure.
    """
    if not text.strip():
        logger.info("[Thread:Ingest] Skipping empty turn node.")
        return None

    if cypher_query is None:
        logger.error("[Thread:Ingest] Graph client is not available.")
        return None

    logger.info(
        f"[Thread:Ingest] Ingesting '{role}' turn for user '{user_id}' in session '{session_id}'.",
    )
    embedding_vector = await _embed_text_3072(text)

    # --- COMPATIBILITY FIX ---
    # Apply both the new, generic labels (Turn, UserInput/AssistantResponse) for
    # future-proofing, and the original legacy labels (SoulInput/SoulResponse)
    # to ensure 100% backward compatibility with existing queries.
    if role == "user":
        labels = ["Turn", "UserInput", "SoulInput"]
    else:  # role == "assistant"
        labels = ["Turn", "AssistantResponse", "SoulResponse"]
    # --- END FIX ---

    properties = {
        "role": role,
        "user_id": user_id,
        "session_id": session_id,
        "episode_id": episode_id,
        "text": text,
        "text_hash": hash(text),
        "char_count": len(text),
        "created_at": now_iso(),
        "timestamp": now(),
        "embedding": embedding_vector,
        "embedding_dims": EXPECTED_DIMS if embedding_vector else 0,
    }

    q = """
    CREATE (t:`{labels}` {{
        id: randomUUID(),
        role: $props.role,
        user_id: $props.user_id,
        session_id: $props.session_id,
        episode_id: $props.episode_id,
        text: $props.text,
        text_hash: $props.text_hash,
        char_count: $props.char_count,
        created_at: datetime($props.created_at),
        timestamp: $props.timestamp,
        embedding: $props.embedding,
        embedding_dims: $props.embedding_dims
    }})
    RETURN t.id AS nodeId
    """.format(labels="`:`".join(labels))

    try:
        result = await cypher_query(q, {"props": properties})
        node_id = result[0]["nodeId"] if result else None
        if node_id:
            logger.info(
                f"[Thread:Ingest] Successfully created Turn node {node_id} with labels: {labels}.",
            )
            return node_id
        logger.error("[Thread:Ingest] Node creation query returned no ID.")
    except Exception as e:
        logger.error(f"[Thread:Ingest] Failed to create Turn node: {e}", exc_info=True)
    return None


async def stitch_narrative_links(
    user_turn_id: str,
    assistant_turn_id: str,
    session_id: str,
) -> None:
    """
    The core "stitching" logic. It creates the causal and temporal links
    that form the narrative.

    1. Links the assistant's response directly to the user's input.
    2. Links the user's input to the *previous* turn in the session.
    """
    if cypher_query is None:
        logger.error("[Thread:Stitch] Graph client is not available.")
        return

    # 1. Link assistant response to the user input that caused it
    # Note: We now match on the generic :Turn label for this internal logic.
    q_response = """
    MATCH (u:Turn {id: $user_turn_id})
    MATCH (a:Turn {id: $assistant_turn_id})
    MERGE (u)-[r:GENERATED_RESPONSE]->(a)
    """
    await cypher_query(
        q_response,
        {"user_turn_id": user_turn_id, "assistant_turn_id": assistant_turn_id},
    )
    logger.info(f"[Thread:Stitch] Linked {user_turn_id} -> {assistant_turn_id}.")

    # 2. Find the previous turn (user or assistant) in the same session and link it
    q_precedes = """
    // Find the most recent turn in this session that is NOT the current user input
    MATCH (prev_turn:Turn {session_id: $session_id})
    WHERE prev_turn.id <> $user_turn_id
    WITH prev_turn ORDER BY prev_turn.timestamp DESC LIMIT 1
    // Find the current user turn
    MATCH (current_user_turn:Turn {id: $user_turn_id})
    // Create the chronological link
    MERGE (prev_turn)-[r:PRECEDES]->(current_user_turn)
    """
    await cypher_query(q_precedes, {"user_turn_id": user_turn_id, "session_id": session_id})
    logger.info(
        f"[Thread:Stitch] Searched for preceding turn for {user_turn_id} in session {session_id}.",
    )


# --------------------------------------------------------------------------
# 🧠 Main Event Processor
# --------------------------------------------------------------------------


async def process_turn_event(event: dict[str, Any]) -> None:
    """
    Main entry point for handling a `voxis.turn.complete` event.
    This function is stateless and idempotent.
    """
    logger.debug(f"[Thread:Event] Received new turn event.")
    if not isinstance(event, dict):
        logger.error("[Thread:Event] Event is not a valid dictionary.")
        return

    try:
        # Safely extract data from the event payload
        payload = event.get("payload", {})
        user_id = event.get("user_id", "unknown_user")
        session_id = event.get("session_id", "unknown_session")
        episode_id = event.get("episode_id")

        user_input_text = payload.get("request", {}).get("user_input", "")
        assistant_response_text = payload.get("final_response", {}).get("expressive_text", "")

        if not user_input_text or not assistant_response_text:
            logger.warning(
                "[Thread:Event] Event is missing user input or assistant response text. Aborting.",
            )
            return

        # --- Core Logic ---
        # 1. Ingest both turns as distinct nodes
        user_turn_id = await ingest_turn_node(
            role="user",
            user_id=user_id,
            session_id=session_id,
            episode_id=episode_id,
            text=user_input_text,
        )
        assistant_turn_id = await ingest_turn_node(
            role="assistant",
            user_id=user_id,  # The assistant acts on behalf of the user session
            session_id=session_id,
            episode_id=episode_id,
            text=assistant_response_text,
        )

        # 2. If both nodes were created, stitch them into the narrative
        if user_turn_id and assistant_turn_id:
            await stitch_narrative_links(user_turn_id, assistant_turn_id, session_id)
            logger.info(
                f"✅ [Thread:Event] Successfully processed and stitched narrative for episode {episode_id}.",
            )
        else:
            logger.error(
                "[Thread:Event] Failed to process narrative; one or both turn nodes could not be created.",
            )

    except Exception as e:
        logger.error(
            f"🚨 [Thread:Event] Unhandled exception while processing turn: {e}",
            exc_info=True,
        )
