# api/endpoints/voxis/talk.py
# FINAL, COMPLETE VERSION — God Plan

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

# The main pipeline which contains the core Ecodia mind logic
from systems.voxis.core.voxis_pipeline import VoxisPipeline

talk_router = APIRouter()

class VoxisTalkRequest(BaseModel):
    user_input: str
    user_id: str
    phrase_event_id: str
    output_mode: str = Field(default="voice", description="The desired output mode: 'voice' or 'typing'")

@talk_router.post("/talk")
async def voxis_chat(req: VoxisTalkRequest, request: Request) -> dict[str, Any]:
    """
    This is the primary conversational endpoint for Ecodia.
    It receives the user's utterance and orchestrates the full pipeline to generate a response.
    """
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="User input cannot be empty.")

    try:
        # 1. Instantiate the pipeline with the request context.
        #    The pipeline now contains all complex logic (Equor, Synapse, Ember calls).
        pipeline = VoxisPipeline(
            user_input=req.user_input,
            user_id=req.user_id,
            phrase_event_id=req.phrase_event_id,
            output_mode=req.output_mode,
        )

        # 2. Run the pipeline to get the fully formed, expressive response.
        response_data = await pipeline.run()

        # 3. Return the structured response to the frontend.
        #    The frontend will use this to decide whether to render voice or typing.
        return response_data

    except Exception as e:
        # The pipeline itself has internal error handling, but we catch any unhandled exceptions here.
        print(f"[Voxis Talk Endpoint] Unhandled exception: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred in the Voxis pipeline.")