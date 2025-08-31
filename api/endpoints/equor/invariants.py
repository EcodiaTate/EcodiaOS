# api/endpoints/equor/invariants.py


from fastapi import APIRouter, HTTPException

from systems.equor.core.identity.invariants import invariant_auditor
from systems.equor.schemas import InvariantCheckResult
from systems.synk.core.switchboard.gatekit import route_gate

invariants_router = APIRouter()


@invariants_router.post(
    "/audit/invariants",
    response_model=list[InvariantCheckResult],
    dependencies=[route_gate("equor.audit.invariants.enabled", True)],
    summary="Run a full audit of all cross-system invariants (Gated)",
)
async def run_system_audit():
    """
    (Gated) Triggers a comprehensive audit of the EcodiaOS identity and
    governance graph against a set of predefined, high-level invariants.
    """
    try:
        results = await invariant_auditor.run_audit()
        return results
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred during the invariant audit: {e!r}",
        )
