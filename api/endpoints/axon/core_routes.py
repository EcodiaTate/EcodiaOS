from __future__ import annotations
import time
from fastapi import APIRouter, Header, HTTPException
from systems.axon.core.act import execute_intent
from systems.axon.schemas import AxonIntent, ActionResult

core_router = APIRouter()

@core_router.get("/health")
async def health():
    return {"status": "ok"}

@core_router.post("/act", response_model=ActionResult)
async def act(intent: AxonIntent, x_decision_id: str | None = Header(default=None)):
    t0 = time.perf_counter()
    try:
        res = await execute_intent(intent, decision_id=x_decision_id)
        # optional: expose elapsed for tracing
        res.counterfactual_metrics = {**(res.counterfactual_metrics or {}), "route_cost_ms": (time.perf_counter()-t0)*1000.0}
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"act_failed: {e}")
