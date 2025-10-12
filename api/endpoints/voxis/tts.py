from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tts_router = APIRouter()

# ---------------------------------------------------------------------
# Hybrid Redis + Local Fallback Store
# ---------------------------------------------------------------------
RESULT_TTL_SECONDS = 3600  # 1 hour
USE_REDIS = True
_local_store: dict[str, dict[str, Any]] = {}

try:
    import redis.asyncio as redis  # type: ignore

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = redis.Redis.from_url(REDIS_URL)
    # We don't eagerly ping here; we'll just try on first operation and fall back if it fails.
    logger.info("[TTS] Redis client initialized (lazy probe).")
except Exception as e:
    logger.warning(f"[TTS] Redis unavailable at import; falling back to in-memory store: {e}")
    USE_REDIS = False
    redis_client = None  # type: ignore


# ---------------------------------------------------------------------
# Store wrapper helpers (safe for Redis or local)
# ---------------------------------------------------------------------
async def store_set(job_id: str, data: dict[str, Any]):
    global USE_REDIS
    if USE_REDIS and redis_client:
        try:
            await redis_client.hset(job_id, mapping=data)
            await redis_client.expire(job_id, RESULT_TTL_SECONDS)
            return
        except Exception as e:
            logger.warning(f"[TTS] Redis set failed; switching to in-memory fallback: {e}")
            USE_REDIS = False
    _local_store[job_id] = {**_local_store.get(job_id, {}), **data}


async def store_get(job_id: str) -> dict[str, str]:
    global USE_REDIS
    if USE_REDIS and redis_client:
        try:
            raw = await redis_client.hgetall(job_id)
            return {k.decode(): v.decode() for k, v in raw.items()}
        except Exception as e:
            logger.warning(f"[TTS] Redis get failed; switching to in-memory fallback: {e}")
            USE_REDIS = False
    # Return a shallow copy to avoid accidental mutation
    return dict(_local_store.get(job_id, {}))


async def store_delete(job_id: str):
    global USE_REDIS
    if USE_REDIS and redis_client:
        try:
            await redis_client.delete(job_id)
            return
        except Exception as e:
            logger.warning(f"[TTS] Redis delete failed; switching to in-memory fallback: {e}")
            USE_REDIS = False
    _local_store.pop(job_id, None)


# ---------------------------------------------------------------------
# Google Cloud Client Setup
# ---------------------------------------------------------------------
try:
    from google.cloud import texttospeech  # type: ignore
    from google.oauth2 import service_account  # type: ignore

    _GOOGLE_CLIENT_AVAILABLE = True
except ImportError:
    _GOOGLE_CLIENT_AVAILABLE = False

# ---------------------------------------------------------------------
# Service Account Key
# ---------------------------------------------------------------------
try:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "../../../"))
    _SA_KEY_PATH = os.path.join(_PROJECT_ROOT, "config", "google_oauth.json")

    _CREDENTIALS = (
        service_account.Credentials.from_service_account_file(_SA_KEY_PATH)
        if _GOOGLE_CLIENT_AVAILABLE and os.path.exists(_SA_KEY_PATH)
        else None
    )
    if not _CREDENTIALS:
        logger.warning(f"[TTS] No Google OAuth key found at {_SA_KEY_PATH}")
except Exception as e:
    logger.error(f"[TTS] Failed to load credentials: {e}")
    _CREDENTIALS = None

# ---------------------------------------------------------------------
# Defaults & Constants
# ---------------------------------------------------------------------
STYLE_PROMPT = (
    "Speak in a calm, genuine, and thoughtful tone with a subtle Australian accent. "
    "The delivery should be conversational and relaxed, with natural pacing and soft pauses."
)
DEFAULT_MODEL = "gemini-2.5-pro-tts"
DEFAULT_LANGUAGE = "en-AU"
DEFAULT_VOICE_NAME = "Leda"
DEFAULT_ENCODING: Literal["LINEAR16"] = "LINEAR16"
DEFAULT_SAMPLE_RATE = 24000
MAX_TTS_TEXT_BYTES = 850
MAX_PROMPT_BYTES = 900
INTERIM_TEXT_CHARS = 250

MEDIA_TYPES = {"LINEAR16": "audio/wav"}


# ---------------------------------------------------------------------
# Helper: Byte-Aware Chunker
# ---------------------------------------------------------------------
def intelligent_chunker(text: str, chunk_byte_limit: int = MAX_TTS_TEXT_BYTES) -> list[str]:
    """
    Splits text into byte-safe chunks under chunk_byte_limit,
    preferring sentence boundaries, falling back to word splitting.
    """
    text = text.strip().replace("\n", " ")
    sentences = re.split(r"(?<=[.?!])\s+", text)
    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        if not sentence:
            continue
        # If a single sentence exceeds the byte limit, split by words
        if len(sentence.encode("utf-8")) > chunk_byte_limit:
            words = sentence.split(" ")
            sub_chunk = ""
            for w in words:
                candidate = (sub_chunk + w + " ").strip() if sub_chunk else (w + " ")
                if len(candidate.encode("utf-8")) > chunk_byte_limit:
                    if sub_chunk:
                        chunks.append(sub_chunk.strip())
                    sub_chunk = w + " "
                else:
                    sub_chunk = candidate
            if sub_chunk:
                chunks.append(sub_chunk.strip())
            continue

        candidate = (current_chunk + sentence + " ").strip() if current_chunk else (sentence + " ")
        if len(candidate.encode("utf-8")) > chunk_byte_limit:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
        else:
            current_chunk = candidate

    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks


# ---------------------------------------------------------------------
# Request Schema
# ---------------------------------------------------------------------
class TTSRequest(BaseModel):
    text: str
    voice_name: str | None = None
    language_code: str = DEFAULT_LANGUAGE
    model_name: str = DEFAULT_MODEL
    prompt_override: str | None = None
    interim_text_override: str | None = None


# ---------------------------------------------------------------------
# Synthesize One Chunk
# ---------------------------------------------------------------------
def synthesize_speech_with_client(
    *,
    prompt: str,
    text: str,
    voice_name: str,
    language_code: str,
    model_name: str,
) -> bytes:
    if not _GOOGLE_CLIENT_AVAILABLE:
        raise RuntimeError("google-cloud-texttospeech not installed.")
    if not _CREDENTIALS:
        raise FileNotFoundError(f"Service account missing: {_SA_KEY_PATH}")

    client = texttospeech.TextToSpeechClient(credentials=_CREDENTIALS)
    synthesis_input = {"prompt": prompt, "text": text}
    voice = {"language_code": language_code, "name": voice_name, "model_name": model_name}
    audio_config = {
        "audio_encoding": texttospeech.AudioEncoding.LINEAR16,
        "sample_rate_hertz": DEFAULT_SAMPLE_RATE,
    }

    response = client.synthesize_speech(
        request={"input": synthesis_input, "voice": voice, "audio_config": audio_config},
        timeout=60.0,
    )
    if not response.audio_content:
        raise ValueError("Google TTS returned empty audio.")
    return response.audio_content


# ---------------------------------------------------------------------
# Background Full Synthesis
# ---------------------------------------------------------------------
async def _run_synthesis_and_store(
    job_id: str,
    full_text: str,
    prompt: str,
    voice_name: str,
    language_code: str,
    model_name: str,
):
    """Chunk long text, synthesize sequentially, store results."""
    try:
        await store_set(job_id, {"status": "processing"})
        logger.info(f"[TTS] Job {job_id} started.")
        text_chunks = intelligent_chunker(full_text)
        full_audio = b""

        for idx, chunk in enumerate(text_chunks, start=1):
            logger.info(f"[TTS] Synthesizing chunk {idx}/{len(text_chunks)} ({len(chunk)} chars).")
            if not chunk:
                continue
            try:
                audio_part = synthesize_speech_with_client(
                    prompt=prompt,
                    text=chunk,
                    voice_name=voice_name,
                    language_code=language_code,
                    model_name=model_name,
                )
                full_audio += audio_part
            except Exception as e:
                logger.warning(f"[TTS] Chunk {idx} failed: {e}")
                continue

        await store_set(job_id, {"status": "succeeded", "audio": full_audio.hex()})
        logger.info(f"[TTS] Job {job_id} completed ({len(full_audio)} bytes).")

    except Exception as e:
        logger.exception(f"[TTS] Job {job_id} failed: {e}")
        await store_set(job_id, {"status": "failed", "error": str(e)})


# ---------------------------------------------------------------------
# POST /synthesize
# ---------------------------------------------------------------------
@tts_router.post("/synthesize")
async def create_synthesis_job(
    req: TTSRequest,
    bg_tasks: BackgroundTasks,
    http_request: Request,
):
    """
    Returns interim audio immediately and schedules full synthesis.
    """
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")

    prompt = (req.prompt_override or STYLE_PROMPT).strip()
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        prompt = prompt.encode("utf-8")[:MAX_PROMPT_BYTES].decode("utf-8", "ignore")

    voice_name = req.voice_name or DEFAULT_VOICE_NAME

    interim_text = req.interim_text_override or text[:INTERIM_TEXT_CHARS]
    if not req.interim_text_override and len(text) > INTERIM_TEXT_CHARS:
        last_space = interim_text.rfind(" ")
        if last_space != -1:
            interim_text = interim_text[:last_space] + "..."

    try:
        interim_audio = synthesize_speech_with_client(
            prompt=prompt,
            text=interim_text,
            voice_name=voice_name,
            language_code=req.language_code,
            model_name=req.model_name,
        )
    except Exception as e:
        logger.error(f"[TTS] Interim synthesis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Interim TTS failed: {e}")

    job_id = str(uuid.uuid4())
    bg_tasks.add_task(
        _run_synthesis_and_store,
        job_id,
        text,
        prompt,
        voice_name,
        req.language_code,
        req.model_name,
    )

    poll_url = str(http_request.url_for("get_synthesis_result", job_id=job_id))
    headers = {
        "Content-Type": "audio/wav",
        "X-Job-ID": job_id,
        "X-Poll-Url": poll_url,
    }

    return Response(content=interim_audio, headers=headers, status_code=202)


# ---------------------------------------------------------------------
# GET /result/{job_id}
# ---------------------------------------------------------------------
@tts_router.get("/result/{job_id}", name="get_synthesis_result")
async def get_synthesis_result(job_id: str):
    result = await store_get(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job ID not found.")

    status = result.get("status")

    if status == "processing":
        return Response(
            content='{"status": "processing"}',
            status_code=202,
            media_type="application/json",
        )

    if status == "failed":
        await store_delete(job_id)
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error."))

    if status == "succeeded":
        audio_hex = result.get("audio")
        if not audio_hex:
            raise HTTPException(status_code=500, detail="No audio stored for job.")
        audio_bytes = bytes.fromhex(audio_hex)
        await store_delete(job_id)
        return Response(content=audio_bytes, media_type="audio/wav")

    raise HTTPException(status_code=500, detail="Unknown job status.")
