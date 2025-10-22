# api/endpoints/voxis/profile.py
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Import the exact functions we moved from the pipeline
from systems.voxis.core.user_profile import (
    normalize_profile_upserts_from_llm,
    upsert_soul_profile_properties,
)

profile_router = APIRouter(tags=["voxis-profile"])


class ProfileConsentRequest(BaseModel):
    user_id: str = Field(..., description="The user's unique identifier.")
    profile_upserts: list[dict[str, Any]] = Field(
        ...,
        description="The raw profile_upserts object from the planner.",
    )


class ProfileConsentResponse(BaseModel):
    status: str = "ok"
    properties_updated: int
    facts_created: int


@profile_router.post("/profile/consent", response_model=ProfileConsentResponse)
async def handle_profile_consent(req: ProfileConsentRequest):
    """
    Receives user consent to save a profile property and persists it.
    """
    if not req.user_id or req.user_id in ("user_anon", "unknown"):
        raise HTTPException(
            status_code=400,
            detail="A valid user_id is required to update a profile.",
        )

    try:
        # We wrap the data in a dictionary to match the shape normalize_... expects
        plan_obj = {"profile_upserts": req.profile_upserts}

        # Sanitize and validate the properties from the client
        properties_to_save = normalize_profile_upserts_from_llm(
            plan_obj,
            user_id=req.user_id,
            min_confidence=0.0,  # Trust the user's explicit consent
        )

        if not properties_to_save:
            return ProfileConsentResponse(properties_updated=0, facts_created=0)

        # Perform the database update
        upserted, facts = await upsert_soul_profile_properties(
            user_id=req.user_id,
            properties=properties_to_save,
            source="user_consent",
            confidence=1.0,  # User explicitly confirmed
        )
        return ProfileConsentResponse(properties_updated=upserted, facts_created=facts)

    except Exception as e:
        print(f"[Profile Consent] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile.")
