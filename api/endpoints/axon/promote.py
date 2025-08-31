# api/endpoints/axon/promote.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from systems.axon.mesh.lifecycle import DriverLifecycleManager
from systems.axon.mesh.promoter import PromotionPolicy, promote_if_ready

promoter_router = APIRouter()


class PromoteRequest(BaseModel):
    driver_name: str = Field(..., description="Driver to evaluate for promotion")
    incumbent_driver: str | None = Field(
        default=None,
        description="Optional incumbent to compare/demote",
    )
    max_p95_ms: int = Field(default=1200)
    min_uplift: float = Field(default=0.02)
    min_window: int = Field(default=50)


@promoter_router.post("/autoroll/promote_if_ready")
async def autoroll_promote_if_ready(req: PromoteRequest) -> dict[str, Any]:
    try:
        ok = await promote_if_ready(
            driver_name=req.driver_name,
            incumbent=req.incumbent_driver,
            policy=PromotionPolicy(
                max_p95_ms=req.max_p95_ms,
                min_uplift=req.min_uplift,
                min_window=req.min_window,
            ),
        )
        state = DriverLifecycleManager().get_state(req.driver_name)
        return {"promoted": ok, "driver": req.driver_name, "status": str(state.status)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"promotion_failed: {e}")
