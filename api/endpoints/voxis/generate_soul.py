# api/endpoints/voxis/generate_soul.py
# Final version with corrected imports + six-word guardrail + response close.

from __future__ import annotations

import asyncio
import json
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# --- Core EcodiaOS Services ---
from core.llm.embeddings_gemini import get_embedding
from core.prompting.orchestrator import build_prompt
from core.security.soul_node_service import encrypt_soulnode
from core.utils.llm_gateway_client import call_llm_service
from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, get_http_client

# --- CORRECTED IMPORTS ---
from systems.synk.core.tools.neo import add_node

generate_router = APIRouter()


class GenerateSoulRequest(BaseModel):
    words: list[str]


# Lightweight set of common glue words we can safely drop to hit exactly 6 words.
_STOPWORDS = {
    "and",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "at",
    "by",
    "from",
    "as",
    "is",
    "are",
    "be",
    "am",
    "was",
    "were",
    "it",
    "this",
    "that",
    "these",
    "those",
    "or",
}


def _extract_soul(bus_data: dict) -> str | None:
    """A robust parser that checks for common alternative keys."""
    json_obj = None
    if isinstance(bus_data.get("json"), dict):
        json_obj = bus_data["json"]
    elif isinstance(bus_data.get("text"), str):
        try:
            text_content = bus_data["text"]
            json_start = text_content.find("{")
            json_end = text_content.rfind("}") + 1
            if 0 <= json_start < json_end:
                json_obj = json.loads(text_content[json_start:json_end])
        except (json.JSONDecodeError, AttributeError):
            pass
    if isinstance(json_obj, dict):
        for key in ["soul", "mantra", "result", "text", "output"]:
            soul = json_obj.get(key)
            if isinstance(soul, str) and soul.strip():
                return soul.strip().strip('"').strip("'")
    return None


def _clean_tail_punct(s: str) -> str:
    # Remove a single trailing mark (.,!?;) to avoid off-by-one splits
    return re.sub(r"[.,!?;]$", "", s).strip()


def _is_valid_soul(soul: str | None) -> bool:
    """Validation: exactly six words."""
    if not soul:
        return False
    words = _clean_tail_punct(soul).split()
    return len(words) == 6


def _coerce_to_six(soul: str | None) -> str | None:
    """
    Guardrail: If model returns >6 words, try to reduce to exactly 6.
    1) Normalize & split
    2) Drop stopwords until len<=6 (preserving order)
    3) If still >6, hard-slice to first 6
    4) If <6 or empty, give up (None)
    """
    if not soul:
        return None
    words = _clean_tail_punct(soul).split()
    if len(words) == 6:
        return " ".join(words)
    if len(words) < 6:  # Too short; don’t fabricate
        return None

    # Try a gentle reduction by dropping common stopwords
    reduced = [w for w in words if w.lower() not in _STOPWORDS]
    if len(reduced) >= 6:
        return " ".join(reduced[:6])

    # If dropping stopwords overshot, fallback to the original but slice to six
    if len(words) >= 6:
        return " ".join(words[:6])

    return None


async def _wait_for_index_update(event_id: str, max_wait_sec: int = 5):
    """Polls the database to ensure the new node is findable in the vector index."""
    print(f"[generate_soul] Waiting for index to update for event_id: {event_id}...")
    start_time = asyncio.get_event_loop().time()
    while True:
        try:
            query = """
            MATCH (sp:SoulNode {event_id: $event_id})
            WITH sp.vector_gemini AS vec
            WHERE vec IS NOT NULL
            CALL db.index.vector.queryNodes('soulnode-gemini-3072', 1, vec) YIELD node
            WHERE node.event_id = $event_id
            RETURN count(node) AS found
            """
            result = await cypher_query(query, {"event_id": event_id})
            if result and result[0].get("found", 0) > 0:
                print("[generate_soul] Index is up to date. Proceeding.")
                return True
        except Exception as e:
            print(f"[generate_soul] Index check warning (will retry): {e}")

        if (asyncio.get_event_loop().time() - start_time) > max_wait_sec:
            print("[generate_soul] ERROR: Timed out waiting for vector index update.")
            return False

        await asyncio.sleep(0.5)


@generate_router.post("/generate_soul")
async def generate_soul(req: GenerateSoulRequest):
    if not isinstance(req.words, list) or not (3 <= len(req.words) <= 10):
        return JSONResponse({"error": "Select between 3 and 10 words."}, status_code=400)

    generated_soul = None

    # Up to 3 attempts (existing behavior), but now with local coercion.
    for attempt in range(3):
        try:
            prompt_data = await build_prompt(
                scope="voxis.soul.generation.v1",
                context={"star_words": req.words},
                summary="Generate exactly six words for the user's Soul.",
            )

            # (Optional) nudge the model toward strict JSON + six words
            prompt_data.messages.append(
                {
                    "role": "system",
                    "content": (
                        'Return ONLY a JSON object like {"soul": "<exactly six words>"}. '
                        "No other keys, no prose, exactly six words."
                    ),
                },
            )

            # Call the gateway (canonical)
            llm_resp = await call_llm_service(
                prompt_response=prompt_data,
                agent_name="Voxis.SoulGenerator",
                scope="voxis.soul.generation.v1",
            )

            # Extract the candidate from either .json or .text
            soul_candidate = _extract_soul_from_llm(llm_resp)

            # First try “as-is” validation
            if _is_valid_soul(soul_candidate):
                generated_soul = _clean_tail_punct(soul_candidate)
                print(f"[generate_soul] Valid soul found on attempt {attempt + 1}.")
                break

            # Then try to coerce to exactly six words
            coerced = _coerce_to_six(soul_candidate)
            if _is_valid_soul(coerced):
                generated_soul = coerced
                print(
                    f"[generate_soul] Coerced to six words on attempt {attempt + 1}: '{generated_soul}'",
                )
                break

            print(
                f"[generate_soul] WARN: Invalid soul received on attempt {attempt + 1}: '{soul_candidate}'",
            )

        except Exception as e:
            print(f"[generate_soul] WARN: Attempt {attempt + 1} failed with exception: {e}")

    if not generated_soul:
        return JSONResponse(
            {"error": "Model failed to generate a valid soul after multiple attempts."},
            status_code=502,
        )

    try:
        encrypted_soul = encrypt_soulnode(generated_soul)
        event_id = str(uuid4())

        await add_node(
            labels=["SoulNode"],
            properties={
                "event_id": event_id,
                "key_id": event_id,
                "words": req.words,
                "soul_encrypted": encrypted_soul,
            },
            embed_text=generated_soul,
        )

        index_ready = await _wait_for_index_update(event_id)
        if not index_ready:
            raise HTTPException(
                status_code=503,
                detail="Could not verify soul in search index. Please try again shortly.",
            )

        return JSONResponse(
            {
                "soul": generated_soul,
                "event_id": event_id,
                "words": req.words,
                "key_id": event_id,
            },
            status_code=200,
        )

    except Exception as e:
        print(f"[generate_soul] Unhandled Exception during persistence: {e}")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during soul storage.",
        )


def _extract_soul_from_llm(llm_resp) -> str:
    """
    Compatible extractor for the gateway response.
    Accepts either llm_resp.json (dict) or llm_resp.text (stringified JSON).
    """
    # Prefer structured JSON
    payload = getattr(llm_resp, "json", None)
    if isinstance(payload, dict):
        val = payload.get("soul")
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Fallback to text and flex-parse
    raw = getattr(llm_resp, "text", "") or ""
    try:
        data = json.loads(raw) if raw.strip().startswith("{") else {}
        val = data.get("soul")
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass

    # Last resort: just return the raw text (caller will coerce/validate)
    return raw.strip()
