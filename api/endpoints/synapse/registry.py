# systems/synapse/api/registry.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

# God Plan Imports
from systems.synapse.core.registry import arm_registry

# Create a dedicated router for registry management.
registry_router = APIRouter(prefix="/registry", tags=["Synapse Registry"])


@registry_router.post("/reload", status_code=202)
async def reload_arm_registry():
    """
    Triggers a full reload of the PolicyArm cache from the Neo4j graph.
    This endpoint is called by other systems, like Simula, after they have
    created a new capability, ensuring the Metacognitive Kernel can
    immediately begin using the new tool.
    """
    print("[Synapse Registry] Received request to reload ArmRegistry from graph.")
    try:
        await arm_registry.initialize()
        return {"status": "accepted", "message": "ArmRegistry reload initiated."}
    except Exception as e:
        print(f"[Synapse Registry] CRITICAL: Failed to reload ArmRegistry: {e}")
        raise HTTPException(status_code=500, detail="Failed to reload ArmRegistry.")
