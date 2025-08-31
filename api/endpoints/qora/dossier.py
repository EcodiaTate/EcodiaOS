# api/endpoints/qora/dossier.py
# MODIFIED FILE
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Import the new, powerful dossier service
from systems.qora.core.code_graph.dossier_service import get_multi_modal_dossier as build_dossier_from_graph

dossier_router = APIRouter()

### --- API Schemas --- ###

class DossierRequest(BaseModel):
    symbol: str = Field(..., description="Fully-qualified name (module/path.py::Class::func)")
    intent: str = Field(..., description="The goal of the request, e.g., 'refactor for clarity'")

class DossierResponse(BaseModel):
    ok: bool
    dossier: dict[str, Any]

### --- Endpoint --- ###

@dossier_router.post("/build", response_model=DossierResponse)
async def dossier_build(req: DossierRequest) -> DossierResponse:
    if not req.symbol:
        raise HTTPException(status_code=400, detail="A target symbol (fqn) is required.")

    try:
        # Call the new graph-based dossier service
        dossier_data = await build_dossier_from_graph(
            target_fqn=req.symbol,
            intent=req.intent
        )

        if "error" in dossier_data:
            raise HTTPException(status_code=404, detail=dossier_data["error"])

        return DossierResponse(ok=True, dossier=dossier_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build dossier: {e!r}")