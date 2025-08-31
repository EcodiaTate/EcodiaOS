# systems/nova/clients/simula_client.py
# --- AMBITIOUS UPGRADE (FIXED PAYLOAD CONTRACT) ---
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# ADD THESE IMPORTS to perform the translation
from api.endpoints.simula.jobs_codegen import CodegenRequest
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.nova.types.patch import SimulaPatchBrief, SimulaPatchTicket


def _resolve(template: str, **params: str) -> str:
    """
    Resolve templated net_api paths like ".../{ticket_id}". 
    If template has no placeholder, append the id when a single param is provided. 
    """
    url = template
    for k, v in params.items():
        placeholder = "{" + k + "}"
        if placeholder in url:
            url = url.replace(placeholder, v)
    if "{" not in url and "}" not in url and len(params) == 1:
        # Append the sole param if not templated
        url = url.rstrip("/") + "/" + next(iter(params.values())) 
    return url


class SimulaClient(BaseModel):
    """
    Simula = codegen & simulation. 
    Nova prepares briefs; Simula writes code. 
    Routed strictly via net_api overlay. 
    """

    async def submit_patch(
        self,
        brief: SimulaPatchBrief,
        *,
        decision_id: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if decision_id:
            headers["x-decision-id"] = decision_id

        # --- START CORRECTION ---
        # Translate the SimulaPatchBrief into the CodegenRequest that the
        # /simula/jobs/codegen endpoint expects. 
        codegen_spec = (
            f"Problem: {brief.problem}\n\n"
            f"Playbook: {brief.playbook}\n\n"
            f"Candidate ID: {brief.candidate_id}"
        )

        # The payload now matches the target endpoint's schema. 
        codegen_request = CodegenRequest(spec=codegen_spec, targets=[])
        payload = codegen_request.model_dump()
        # --- END CORRECTION ---

        client = await get_http_client()
        # The endpoint key should be SIMULA_JOBS_CODEGEN
        r = await client.post(ENDPOINTS.SIMULA_JOBS_CODEGEN, json=payload, headers=headers)
        r.raise_for_status()
        return dict(r.json())

    async def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        client = await get_http_client()
        # Corrected this to use a more robust check for the endpoint key
        ticket_endpoint = getattr(ENDPOINTS, "SIMULA_PATCH_TICKET", "/simula/patches/{ticket_id}")
        url = _resolve(ticket_endpoint, ticket_id=ticket_id)
        r = await client.get(url)
        r.raise_for_status()
        return dict(r.json()) 