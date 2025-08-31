# api/endpoints/voxis/match_phrase.py
# Upgraded with cryptographic verification.

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query
from core.security.soul_phrase_service import verify_soulphrase # <-- Import our new verifier

match_router = APIRouter()

INDEX_NAME = "soulphrase-gemini-3072"
TOP_K = 1 # We only want the single best match to verify

@match_router.post("/match_phrase")
async def match_phrase(request: Request):
    try:
        payload = await request.json()
        phrase_in = (payload.get("phrase") or "").strip()
        if not phrase_in:
            return JSONResponse({"error": "No phrase provided"}, status_code=400)

        # 1. Embed the user's input to find the most likely candidate node
        vec = await get_embedding(phrase_in)
        
        # 2. Vector search for the top candidate
        rows = await cypher_query(
            "CALL db.index.vector.queryNodes($index, $k, $vec) YIELD node, score RETURN node",
            {"index": INDEX_NAME, "k": TOP_K, "vec": vec},
        )

        if not rows:
            return JSONResponse({"error": "No matching constellation found."}, status_code=404)

        node = rows[0].get("node", {})
        stored_encrypted_phrase = node.get("phrase_encrypted")
        
        if not stored_encrypted_phrase:
            return JSONResponse({"error": "Matched node is missing secure phrase."}, status_code=500)
            
        if verify_soulphrase(phrase_in, stored_encrypted_phrase):
            words = node.get("words") # <-- Check for words *before* returning

            return JSONResponse({
                "words": words,
                "event_id": node.get("event_id"),
                "key_id": node.get("key_id"),
                "message": "Verification successful."
            }, status_code=200)
        else:
            return JSONResponse({"error": "No matching constellation found."}, status_code=404)

    except Exception as e:
        print(f"[match_phrase] Error: {e}")
        return JSONResponse({"error": "An unexpected error occurred during matching."}, status_code=500)
