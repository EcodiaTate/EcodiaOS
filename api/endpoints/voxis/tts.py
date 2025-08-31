# api/endpoints/tts.py

from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
import httpx
import os

tts_router = APIRouter()

# --- Configuration ---
# These should be set in your environment (e.g., in D:\EcodiaOS\config\.env)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ECODIA_VOICE_ID = os.getenv("ECODIA_VOICE_ID") # The ID for the specific voice you've chosen for Ecodia

class TTSRequest(BaseModel):
    # The text now includes all expressive tags like "[sighs] [softly]"
    text: str
    voice_id: str | None = None

@tts_router.post("/generate")
async def generate_speech(req: TTSRequest, request: Request):
    """
    Receives text with embedded expressive tags and generates speech via ElevenLabs.
    """
    if not ELEVENLABS_API_KEY or not ECODIA_VOICE_ID:
        raise HTTPException(status_code=500, detail="ElevenLabs API key or Voice ID is not configured on the server.")

    voice_id = req.voice_id or ECODIA_VOICE_ID
    # We use the v1 endpoint which supports the new bracketed instruction style
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }

    # The payload is now incredibly simple. We pass the raw text with tags.
    # The 'eleven_multilingual_v2' model is good at interpreting these contextual cues.
    payload = {
        "text": req.text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.5, # A moderate base style, allowing tags to do the heavy lifting
            "use_speaker_boost": True,
        },
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=60.0)
            response.raise_for_status() # Will raise an exception for 4xx/5xx responses
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"An error occurred while requesting ElevenLabs: {exc}")

    # Return the raw audio file to the frontend
    return Response(content=response.content, media_type="audio/mpeg")