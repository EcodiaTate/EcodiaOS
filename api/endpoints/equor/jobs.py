# api/endpoints/equor/jobs.py
import logging

from fastapi import APIRouter, BackgroundTasks, status

# Import the actual batch job function
from systems.equor.jobs.soulsynth_batch import run_batch

logger = logging.getLogger(__name__)
jobs_router = APIRouter(tags=["equor-jobs"])


@jobs_router.post("/soulsynth/run-batch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_soulsynth_batch(background_tasks: BackgroundTasks):
    """
    Triggers the SoulSynth batch job to run in the background.

    Returns an immediate 202 Accepted response.
    """
    logger.info("[Equor Jobs] Received request to start SoulSynth batch job.")

    # Use FastAPI's built-in background tasks to run the job.
    # This allows the endpoint to return a response immediately.
    background_tasks.add_task(run_batch)

    return {
        "status": "accepted",
        "message": "SoulSynth batch job has been scheduled to run in the background. Check server logs for progress.",
    }
