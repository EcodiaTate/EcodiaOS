# systems/synapse/api/models.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from systems.synapse.world.simulator import world_model  # singleton used elsewhere

# (No new training code here; just a thin API wrapper.)

router = APIRouter(prefix="/models", tags=["Synapse Models"])


class PredictRequest(BaseModel):
    model_id: str = Field(..., description="Logical model name (routing only).")
    inputs: dict[str, Any] = Field(..., description="Arbitrary model-specific inputs.")


class PredictResponse(BaseModel):
    predicted_state_vector: list[float] | None = None
    raw: dict[str, Any] | None = None


@router.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest):
    """
    Thin, best-effort prediction shim:
      - If world_model exposes a compatible method, use it.
      - Else return inputs untouched (raw), so callers can still proceed.
    """
    try:
        inputs = req.inputs or {}
        state = inputs.get("current_state_vector")
        ctx = inputs.get("task_context_features", {})

        # Try common method names without coupling tightly to implementation.
        for name in ("predict_next_state", "predict_state", "simulate_one_step", "simulate"):
            fn = getattr(world_model, name, None)
            if callable(fn):
                out = fn(state, ctx)
                # Support async/await if provided
                if hasattr(out, "__await__"):
                    out = await out
                if isinstance(out, list | tuple) and all(isinstance(x, int | float) for x in out):
                    return PredictResponse(predicted_state_vector=[float(x) for x in out])
                if isinstance(out, dict) and "predicted_state_vector" in out:
                    v = out["predicted_state_vector"]
                    if isinstance(v, list):
                        return PredictResponse(
                            predicted_state_vector=[float(x) for x in v],
                            raw=out,
                        )

        # Fallback — no compatible world_model method
        return PredictResponse(
            predicted_state_vector=None,
            raw={"passthrough": True, "inputs": inputs},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e!r}")
