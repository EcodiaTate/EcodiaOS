# api/endpoints/voxis/match_soul.py
# Upgraded with cryptographic verification.

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.llm.embeddings_gemini import get_embedding
from core.security.soul_node_service import verify_soulnode  # <-- Import our new verifier
from core.utils.neo.cypher_query import cypher_query

match_router = APIRouter()

INDEX_NAME = "soulnode-gemini-3072"
TOP_K = 1  # We only want the single best match to verify


@match_router.post("/match_soul")
async def match_soul(request: Request):
    try:
        payload = await request.json()
        soul_in = (payload.get("soul") or "").strip()
        if not soul_in:
            return JSONResponse({"error": "No soul provided"}, status_code=400)

        # 1. Embed the user's input to find the most likely candidate node
        vec = await get_embedding(soul_in)

        # 2. Vector search for the top candidate
        rows = await cypher_query(
            "CALL db.index.vector.queryNodes($index, $k, $vec) YIELD node, score RETURN node",
            {"index": INDEX_NAME, "k": TOP_K, "vec": vec},
        )

        if not rows:
            return JSONResponse({"error": "No matching constellation found."}, status_code=404)

        node = rows[0].get("node", {})
        stored_encrypted_soul = node.get("soul_encrypted")

        if not stored_encrypted_soul:
            return JSONResponse({"error": "Matched node is missing secure soul."}, status_code=500)

        if verify_soulnode(soul_in, stored_encrypted_soul):
            words = node.get("words")  # <-- Check for words *before* returning

            return JSONResponse(
                {
                    "words": words,
                    "event_id": node.get("event_id"),
                    "key_id": node.get("key_id"),
                    "message": "Verification successful.",
                },
                status_code=200,
            )
        else:
            return JSONResponse({"error": "No matching constellation found."}, status_code=404)

    except Exception as e:
        print(f"[match_soul] Error: {e}")
        return JSONResponse(
            {"error": "An unexpected error occurred during matching."},
            status_code=500,
        )


@match_router.post("/reencrypt_soulnodes")
async def reencrypt_all_souls():
    from core.security.soul_node_service import reencrypt_if_legacy
    from core.utils.neo.neo_driver import get_driver  # uses your global AsyncDriver

    updated = 0
    failed = 0

    driver = get_driver()

    async with driver.session() as session:
        result = await session.run("MATCH (n:SoulNode) RETURN id(n) AS id, n.soul_encrypted AS val")
        rows = await result.data()

        for row in rows:
            node_id = row["id"]
            old = row["val"]
            try:
                new, changed = reencrypt_if_legacy(old)
                if changed:
                    await session.run(
                        "MATCH (n) WHERE id(n) = $id SET n.soul_encrypted = $new",
                        {"id": node_id, "new": new},
                    )
                    updated += 1
            except Exception as e:
                print(f"Failed to reencrypt {node_id}: {e}")
                failed += 1

    return {"updated": updated, "failed": failed}


@match_router.post("/admin/upsert_soulnode")
async def admin_upsert_soulnode(payload: dict):
    """
    Body: { "uuid": "<uuid of your node>", "soul": "<the plaintext soul>" }
    - Encrypts with current default cipher (AES-GCM given your env)
    - Recomputes the embedding
    - Updates existing node (MERGE by uuid) without touching other props
    """
    from core.llm.embeddings_gemini import get_embedding
    from core.security.soul_node_service import encrypt_soulnode
    from core.utils.neo.neo_driver import get_driver

    uuid = (payload.get("uuid") or "").strip()
    soul = (payload.get("soul") or "").strip()
    if not uuid or not soul:
        return JSONResponse({"error": "uuid and soul required"}, status_code=400)

    enc = encrypt_soulnode(soul)
    vec = await get_embedding(soul)

    driver = get_driver()
    async with driver.session() as session:
        await session.run(
            """
          MERGE (n:SoulNode {uuid: $uuid})
          SET n.soul_encrypted = $enc,
              n.vector_gemini   = $vec,
              n.words           = $words,
              n.key_id          = coalesce(n.key_id, $uuid),
              n.event_id        = coalesce(n.event_id, $uuid),
              n.updated_at      = datetime()
        """,
            {
                "uuid": uuid,
                "enc": enc,
                "vec": vec,
                # keep your existing words if you want; otherwise derive a simple token list:
                "words": [
                    w for w in "".join(c if c.isalpha() else " " for c in soul.lower()).split()
                ][:10],
            },
        )

    return {"ok": True, "uuid": uuid}
