# systems/axon/mesh/synthesis_client.py
from __future__ import annotations

from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.axon.dependencies import get_lifecycle_manager


async def request_driver_synthesis(
    *,
    driver_name: str,
    api_spec_url: str | None = None,
    template_hint: str | None = None,
    artifact_dir: str | None = None,
) -> dict[str, Any]:
    """
    Requests Simula to synthesize a driver from a spec/hint, then records the job in lifecycle.
    """
    client = await get_http_client()
    path = getattr(ENDPOINTS, "SIMULA_DRIVER_SYNTH", None) or getattr(
        ENDPOINTS, "SIMULA_CODEGEN", "/simula/driver/synth"
    )
    payload = {
        "driver_name": driver_name,
        "api_spec_url": api_spec_url,
        "template_hint": template_hint,
    }
    r = await client.post(path, json=payload)
    r.raise_for_status()
    data = r.json()

    job_id = str(data.get("job_id") or data.get("id") or "")
    artifacts = str(data.get("artifact_path") or (artifact_dir or "systems/axon/drivers/generated"))

    lifecycle = get_lifecycle_manager()
    lifecycle.record_synthesis_job(driver_name=driver_name, job_id=job_id, artifact_path=artifacts)

    return {"job_id": job_id, "artifact_path": artifacts, "status": "submitted"}
