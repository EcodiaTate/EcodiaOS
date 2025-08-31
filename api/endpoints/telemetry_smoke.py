# D:\EcodiaOS\api\endpoints\telemetry_smoke.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from core.telemetry.decorators import episode
from core.utils.net_api import get_http_client
from core.services.synapse import SynapseClient
from systems.synapse.schemas import Candidate, TaskContext

dev_telemetry_router = APIRouter()


@dev_telemetry_router.get("/telemetry/smoke")
@episode("telemetry.smoke")
async def telemetry_smoke() -> dict[str, Any]:
    """
    Dev-only: binds an episode via select_arm, makes a few outbound calls
 
    (harvests headers), then the @episode decorator writes the outcome.
    """
    # 1) Bind the episode by selecting an arm
    syn = SynapseClient()
    task_ctx = TaskContext(
        task_key="telemetry.smoke",
        budget_ms=5000,
    )  # budget shows up as allocated_ms
    _ = await syn.select_arm(task_ctx, candidates=[Candidate(id="noop_safe_planful", content={})])

    # 2) Make some outbound requests that emit timing headers
    client = await get_http_client()
    # Axon path stamps X-Axon-Action-Cost-MS; do a few calls to get non-zero sums
    
    for _ in range(3):
        await client.get("/axon/meta/telemetry")
    # Any route adds X-Cost-MS
    await client.get("/api/health")

    # 3) Return something small — the @episode decorator will write the outcome once.
    return {"ok": True}