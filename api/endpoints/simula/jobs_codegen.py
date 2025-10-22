# api/endpoints/simula/jobs_codegen.py
import logging
import time
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response

from systems.simula.agent.scl_orchestrator import SCL_Orchestrator  # <-- NEW
from systems.simula.nscs.agent_tools import get_context_dossier
from systems.simula.schema import SimulaCodegenIn, SimulaCodegenOut, SimulaCodegenTarget
from systems.synk.core.switchboard.gatekit import route_gate

from ._helpers import _derive_target_fqn  # Assuming helpers exist

codegen_router = APIRouter()
log = logging.getLogger("simula.api.codegen")


@codegen_router.post(
    "/jobs/codegen",
    dependencies=[route_gate("simula.codegen.enabled", True)],
    response_model=SimulaCodegenOut,
    summary="Activate the Simula Synaptic Control Loop",
)
async def start_agent_job(req: SimulaCodegenIn, response: Response) -> SimulaCodegenOut:
    request_id = uuid4().hex
    session_id = req.session_id or uuid4().hex
    response.headers["X-Request-ID"] = request_id
    t0 = time.perf_counter()

    graph_fqn, _, first_path = _derive_target_fqn(req.targets, req.spec)
    log.info("start codegen req_id=%s goal='%s' target_fqname=%s", request_id, req.spec, graph_fqn)

    # Prepare the context BEFORE calling the orchestrator
    dossier = {}
    if graph_fqn:
        log.info("Fetching context dossier for target: %s", graph_fqn)
        try:
            dossier_response = await get_context_dossier(
                target_fqname=graph_fqn,
                intent="implement",
            )
            if dossier_response.get("status") == "success":
                dossier = dossier_response.get("result", {}).get("dossier", {})
            else:
                log.warning(
                    "Could not get dossier for '%s': %s.",
                    graph_fqn,
                    dossier_response.get("reason", ""),
                )
        except Exception as e:
            log.error("Exception while fetching dossier: %s", e, exc_info=True)

    try:
        # Instantiate and run the SCL Orchestrator
        orchestrator = SCL_Orchestrator(session_id=session_id)
        result = await orchestrator.run(
            goal=req.spec,
            dossier=dossier,
            target_fqname=graph_fqn,
        )

    except Exception as e:
        log.exception("req_id=%s exception during SCL orchestration", request_id)
        raise HTTPException(status_code=500, detail=f"SCL Orchestrator failed: {e!r}")

    # Handle the response
    duration = round(time.perf_counter() - t0, 3)
    status = (result or {}).get("status", "unknown")
    message = (result or {}).get("reason") or (result or {}).get("deliberation", {}).get("reason")

    response.headers["X-Job-Status"] = status
    if graph_fqn:
        response.headers["X-Target-FQN"] = graph_fqn
    if first_path:
        response.headers["X-Target-Path"] = first_path

    log.info("finish codegen req_id=%s status=%s duration=%.3fs", request_id, status, duration)
    return SimulaCodegenOut(job_id=request_id, status=status, message=message)
