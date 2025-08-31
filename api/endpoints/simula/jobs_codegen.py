# api/endpoints/simula/jobs_codegen.py
# FINAL: collision-proof & pydantic v2 safe
# NOTE: intentionally NO "from __future__ import annotations" so annotations are concrete.

import logging
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, ConfigDict

# If you actually need this, keep it; otherwise comment it out while debugging
from systems.synk.core.switchboard.gatekit import route_gate

codegen_router = APIRouter()
log = logging.getLogger("simula.api.codegen")

# ---------- MODELS (unique names to avoid collisions) ----------

class SimulaCodegenTarget(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str = Field(..., description="Repo-relative path")
    signature: str | None = None

class SimulaCodegenIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    spec: str = Field(..., min_length=10)
    targets: list[SimulaCodegenTarget] = Field(default_factory=list)
    budget_ms: int | None = None

class SimulaCodegenOut(BaseModel):
    job_id: str
    status: str
    message: str | None = None

# Import-time sanity: if any of these aren’t classes, explode now.
assert isinstance(SimulaCodegenIn, type) and issubclass(SimulaCodegenIn, BaseModel), "SimulaCodegenIn shadowed!"
assert isinstance(SimulaCodegenOut, type) and issubclass(SimulaCodegenOut, BaseModel), "SimulaCodegenOut shadowed!"
# --- sanity: model_fields must be a dict (pydantic v2) ---

if callable(SimulaCodegenIn.model_fields):
    mf = SimulaCodegenIn.model_fields
   
    # blow up right here so you get a clean import-time traceback
    raise RuntimeError("[DIAG] SimulaCodegenIn.model_fields was replaced by a function")

assert isinstance(SimulaCodegenIn.model_fields, dict), "model_fields must be a dict on v2"

# --- Back-compat exports for old imports ---
CodegenRequest  = SimulaCodegenIn
CodegenResponse = SimulaCodegenOut
__all__ = ["SimulaCodegenIn", "SimulaCodegenOut", "CodegenRequest", "CodegenResponse", "start_agent_job", "codegen_router"]

# ---------- ROUTE ----------

@codegen_router.post(
    "/jobs/codegen",
    dependencies=[route_gate("simula.codegen.enabled", True)],
    response_model=SimulaCodegenOut,  # now explicit & safe
    summary="Activate the Simula Strategic Agent",
)
async def start_agent_job(req: SimulaCodegenIn, response: Response) -> SimulaCodegenOut:
    """
    Activates the Simula agent to achieve the specified goal ('spec').
    """
    from systems.simula.agent.orchestrator_main import AgentOrchestrator  # keep import local

    request_id = uuid4().hex
    response.headers["X-Request-ID"] = request_id
    t0 = time.perf_counter()

    log.info("start codegen req_id=%s goal='%s' hints=%d", request_id, req.spec, len(req.targets))

    objective_dict = {
        "id": f"obj_{request_id}",
        "title": (req.spec or "Untitled Codegen Task")[:120],
        "description": req.spec,
        "initial_hints": [t.model_dump() for t in req.targets],
    }

    try:
        agent = AgentOrchestrator()
        result = await agent.run(
            goal=req.spec,
            objective_dict=objective_dict,
            budget_ms=req.budget_ms,
        )
    except Exception as e:
        log.exception("req_id=%s exception during agent run", request_id)
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e!r}")

    duration = round(time.perf_counter() - t0, 3)
    status = (result or {}).get("status", "unknown")
    message = (result or {}).get("message") or (result or {}).get("reason")

    log.info("finish codegen req_id=%s status=%s duration=%.3fs", request_id, status, duration)
    response.headers["X-Job-Status"] = status

    return SimulaCodegenOut(job_id=request_id, status=status, message=message)
