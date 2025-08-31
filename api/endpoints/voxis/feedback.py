# api/endpoints/voxis/feedback.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.services.synapse import synapse
from core.utils.neo.cypher_query import cypher_query

feedback_router = APIRouter()

class FeedbackRequest(BaseModel):
    episode_id: str
    utility: float = Field(..., ge=0.0, le=1.0, description="User feedback: 1.0 for positive, 0.0 for negative.")
    chosen_arm_id: str


@feedback_router.post("/feedback")
async def log_feedback(req: FeedbackRequest):
    """
    Receives explicit user feedback and enriches it with tool-use success,
    providing a powerful learning signal to Synapse.
    """
    try:
        # 1. Fetch the original episode to see if a tool was used
        query = "MATCH (e:Episode {id: $episode_id}) RETURN e.metrics AS metrics"
        result = await cypher_query(query, {"episode_id": req.episode_id})
        episode_metrics = (result[0].get("metrics") if result else {}) or {}

        # 2. Construct the final metrics payload
        final_metrics = {
            "chosen_arm_id": req.chosen_arm_id,
            "utility": req.utility,
            "feedback_source": "user_explicit",
            # If a tool was used, the user's feedback directly rates its success
            "tool_use_success": req.utility if episode_metrics.get("tool_used") else None
        }

        # 3. Log the enriched outcome to Synapse
        await synapse.log_outcome(
            episode_id=req.episode_id,
            task_key=req.task_key,
            metrics=final_metrics
        )
        return {"status": "ok", "message": f"Enriched feedback logged."}

    except Exception as e:
        print(f"[Feedback Endpoint] Error logging outcome: {e}")
        return {"status": "error", "message": "Could not log feedback."}