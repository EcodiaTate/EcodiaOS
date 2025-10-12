# scripts/seed_soul_node.py
# Restore/seed a SoulNode with precise properties (encrypt plaintext, compute vector).

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, List, Optional

from dotenv import load_dotenv

from core.llm.embeddings_gemini import get_embedding
from core.security.soul_node_service import encrypt_soulnode
from core.utils.neo.cypher_query import cypher_query
from core.utils.neo.neo_driver import close_driver, init_driver

load_dotenv()  # env for keys, drivers, etc.

# ----------------------------
# Fixed values (from your snapshot)
# ----------------------------
RESTORE_UUID = "d5a154c5-0f41-4a04-ba72-e0e36f56aa2f"
RESTORE_EVENT_ID = "d5a154c5-0f41-4a04-ba72-e0e36f56aa2f"
RESTORE_KEY_ID = "d5a154c5-0f41-4a04-ba72-e0e36f56aa2f"

# Exact ISO8601 with Z (kept from your node)
RESTORE_CREATED_AT = "2025-09-03T09:48:59.671000000Z"
RESTORE_UPDATED_AT = "2025-10-05T07:31:15.767000000Z"

# Plaintext to encrypt and embed (your request)
PLAINTEXT_SOUL = "FCCHITW120909"

# Derived words for your node; you asked to keep it exactly ["fcchitw"]
RESTORE_WORDS: list[str] = ["fcchitw"]
# ----------------------------


def _iso_to_datetime_str(iso_str: str) -> str:
    """
    Normalize ISO8601 with 'Z' to a string Neo4j datetime() accepts.
    We will pass it as a string into datetime($param).
    """
    s = iso_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        dt = datetime.now(UTC)
    return dt.replace(tzinfo=UTC).isoformat()


async def seed_or_restore_soulnode() -> None:
    # 1) Encrypt the plaintext using configured cipher (AES-GCM preferred by your setup)
    if not PLAINTEXT_SOUL.strip():
        raise ValueError("PLAINTEXT_SOUL cannot be empty.")
    soul_encrypted = encrypt_soulnode(PLAINTEXT_SOUL.strip(), aad={})
    print("[INFO] Encrypted soul from plaintext.")

    # 2) Compute the vector from the plaintext (retrieval document mode)
    try:
        vector = await get_embedding(PLAINTEXT_SOUL.strip(), task_type="RETRIEVAL_DOCUMENT")
        if not isinstance(vector, list) or not vector:
            raise RuntimeError("Embedding call returned an invalid vector.")
        print(f"[INFO] Computed vector_gemini of length {len(vector)}.")
    except Exception as e:
        raise RuntimeError(f"Embedding failed; cannot proceed without vector. Error: {e}") from e

    # 3) Timestamps -> canonical ISO strings Neo understands
    created_at = _iso_to_datetime_str(RESTORE_CREATED_AT)
    updated_at = _iso_to_datetime_str(RESTORE_UPDATED_AT)

    # 4) Write the node with exact properties (and set vector_gemini)
    q = """
    MERGE (n:SoulNode {uuid:$uuid})
    ON CREATE SET
      n.created_at = datetime($created_at)
    SET
      n.event_id       = $event_id,
      n.key_id         = $key_id,
      n.soul_encrypted = $soul_encrypted,
      n.words          = $words,
      n.updated_at     = datetime($updated_at),
      n.vector_gemini  = $vector
    RETURN elementId(n) AS id, labels(n) AS labels
    """
    params: dict[str, Any] = {
        "uuid": RESTORE_UUID,
        "event_id": RESTORE_EVENT_ID,
        "key_id": RESTORE_KEY_ID,
        "soul_encrypted": soul_encrypted,
        "words": RESTORE_WORDS,
        "created_at": created_at,
        "updated_at": updated_at,
        "vector": vector,
    }

    print("[INFO] Writing SoulNode with precise properties…")
    rows = await cypher_query(q, params)
    if not rows:
        raise RuntimeError("No result returned from MERGE; write may have failed.")
    rid = rows[0].get("id")
    print(f"[SUCCESS] SoulNode restored. elementId={rid}")

    # 5) Sanity readback
    sanity_q = """
    MATCH (n:SoulNode {uuid:$uuid})
    RETURN n.uuid AS uuid, n.event_id AS event_id, n.key_id AS key_id,
           n.created_at AS created_at, n.updated_at AS updated_at,
           n.words AS words, size(coalesce(n.vector_gemini, [])) AS vector_len,
           n.soul_encrypted AS soul_encrypted
    """
    back = await cypher_query(sanity_q, {"uuid": RESTORE_UUID})
    if back:
        b = back[0]
        print("[READBACK]")
        print(f"  uuid        : {b.get('uuid')}")
        print(f"  event_id    : {b.get('event_id')}")
        print(f"  key_id      : {b.get('key_id')}")
        print(f"  created_at  : {b.get('created_at')}")
        print(f"  updated_at  : {b.get('updated_at')}")
        print(f"  words       : {b.get('words')}")
        print(f"  vector_len  : {b.get('vector_len')}")
        # avoid dumping full secret; show prefix only
        enc = b.get("soul_encrypted")
        print("  soul_encrypted (prefix):", (enc[:80] + "…") if isinstance(enc, str) else enc)


if __name__ == "__main__":

    async def main():
        await init_driver()
        try:
            await seed_or_restore_soulnode()
        finally:
            await close_driver()

    asyncio.run(main())
