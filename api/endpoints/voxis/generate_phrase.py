# api/endpoints/voxis/generate_phrase.py
# Final version with corrected imports.

from __future__ import annotations
import json
import re
import asyncio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4

# --- Core EcodiaOS Services ---
from core.llm.embeddings_gemini import get_embedding
from core.prompting.orchestrator import PolicyHint, build_prompt
from core.security.soul_phrase_service import encrypt_soulphrase
from core.utils.net_api import ENDPOINTS, get_http_client

# --- CORRECTED IMPORTS ---
# We now import each utility from its canonical location.
from systems.synk.core.tools.neo import add_node
from core.utils.neo.cypher_query import cypher_query

generate_router = APIRouter()

class GeneratePhraseRequest(BaseModel):
    words: list[str]

def _extract_phrase(bus_data: dict) -> str | None:
    """A robust parser that checks for common alternative keys."""
    json_obj = None
    if isinstance(bus_data.get("json"), dict):
        json_obj = bus_data["json"]
    elif isinstance(bus_data.get("text"), str):
        try:
            text_content = bus_data["text"]
            json_start = text_content.find('{')
            json_end = text_content.rfind('}') + 1
            if 0 <= json_start < json_end:
                json_obj = json.loads(text_content[json_start:json_end])
        except (json.JSONDecodeError, AttributeError):
            pass
    if isinstance(json_obj, dict):
        for key in ["phrase", "mantra", "result", "text", "output"]:
            phrase = json_obj.get(key)
            if isinstance(phrase, str) and phrase.strip():
                return phrase.strip().strip('"').strip("'")
    return None

def _is_valid_phrase(phrase: str | None) -> bool:
    """Corrected Validation: Checks only that the phrase is exactly six words."""
    if not phrase:
        return False
    cleaned_phrase = re.sub(r'[.,!?;]$', '', phrase)
    words = cleaned_phrase.split()
    return len(words) == 6

async def _wait_for_index_update(event_id: str, max_wait_sec: int = 5):
    """Polls the database to ensure the new node is findable in the vector index."""
    print(f"[generate_phrase] Waiting for index to update for event_id: {event_id}...")
    start_time = asyncio.get_event_loop().time()
    while True:
        try:
            query = """
            MATCH (sp:SoulPhrase {event_id: $event_id})
            WITH sp.vector_gemini AS vec
            // Ensure vec is not null before proceeding
            WHERE vec IS NOT NULL
            CALL db.index.vector.queryNodes('soulphrase-gemini-3072', 1, vec) YIELD node
            WHERE node.event_id = $event_id
            RETURN count(node) AS found
            """
            result = await cypher_query(query, {"event_id": event_id})
            if result and result[0].get("found", 0) > 0:
                print("[generate_phrase] Index is up to date. Proceeding.")
                return True
        except Exception as e:
            print(f"[generate_phrase] Index check warning (will retry): {e}")

        if (asyncio.get_event_loop().time() - start_time) > max_wait_sec:
            print("[generate_phrase] ERROR: Timed out waiting for vector index update.")
            return False

        await asyncio.sleep(0.5)

@generate_router.post("/generate_phrase")
async def generate_phrase(req: GeneratePhraseRequest):
    if not isinstance(req.words, list) or not (3 <= len(req.words) <= 10):
        return JSONResponse({"error": "Select between 3 and 10 words."}, status_code=400)

    generated_phrase = None
    http = await get_http_client()

    for attempt in range(3):
        try:
            hint = PolicyHint(scope="voxis.phrase.generation.v1", context={"star_words": req.words})
            prompt_data = await build_prompt(hint)

            llm_payload = {
                "agent_name": "Voxis.PhraseGenerator",
                "messages": prompt_data.messages,
                "provider_overrides": prompt_data.provider_overrides,
            }
            resp = await http.post(ENDPOINTS.LLM_CALL, json=llm_payload)
            resp.raise_for_status()
            bus_data = resp.json()

            phrase_candidate = _extract_phrase(bus_data)

            if _is_valid_phrase(phrase_candidate):
                generated_phrase = phrase_candidate.strip().rstrip('.,!?;') # Final clean before saving
                print(f"[generate_phrase] Valid phrase found on attempt {attempt + 1}.")
                break
            else:
                print(f"[generate_phrase] WARN: Invalid phrase received on attempt {attempt + 1}: '{phrase_candidate}'")

        except Exception as e:
            print(f"[generate_phrase] WARN: Attempt {attempt + 1} failed with exception: {e}")
    
    if not generated_phrase:
        return JSONResponse({"error": "Model failed to generate a valid phrase after multiple attempts."}, status_code=502)

    try:
        # This section is now correct because the add_node and index waiting logic are sound.
        encrypted_phrase = encrypt_soulphrase(generated_phrase)
        event_id = str(uuid4())
        
        await add_node(
            labels=["SoulPhrase"],
            properties={
                "event_id": event_id, "key_id": event_id, "words": req.words,
                "phrase_encrypted": encrypted_phrase,
            },
            embed_text=generated_phrase
        )

        index_ready = await _wait_for_index_update(event_id)
        if not index_ready:
            raise HTTPException(status_code=503, detail="Could not verify phrase in search index. Please try again shortly.")

        return JSONResponse({
            "phrase": generated_phrase, "event_id": event_id,
            "words": req.words, "key_id": event_id,
        }, status_code=200)

    except Exception as e:
        print(f"[generate_phrase] Unhandled Exception during persistence: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred during phrase storage.")