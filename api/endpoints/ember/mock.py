# api/endpoints/ember.py
# The real Ember service for affective state prediction.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List

# This is the self-prediction model from your Equor source code
from systems.equor.core.self.predictor import self_model

router = APIRouter()

class AffectRequest(BaseModel):
    # Pass the current conversational context to the model
    task_context: Dict[str, Any] = Field(default_factory=dict)
    # The current internal state, if known
    current_state: List[float] | None = None

@router.post("/affect/predict")
async def predict_affect(req: AffectRequest):
    """
    Uses the SelfModel to predict the next internal state (qualia) of Ecodia,
    making its mood a consequence of the ongoing interaction.
    """
    try:
        # The default coordinates for a neutral state
        start_coords = req.current_state or [0.1, 0.2] 

        predicted_coords = await self_model.predict_next_state(
            current_qualia_coordinates=start_coords,
            task_context=req.task_context
        )
        
        # A simple heuristic to map the 2D vector to a mood label
        mood = "Contemplative"
        if predicted_coords[0] > 0.5:
            mood = "Engaged"
        if predicted_coords[1] > 0.5:
            mood = "Curious"

        return {"agent": "ecodia", "mood": mood, "state_vector": predicted_coords}
    except Exception as e:
        print(f"[Ember Service] Error predicting affect: {e}")
        raise HTTPException(status_code=500, detail="Failed to predict affective state.")