from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field # REFACTORED: Import Pydantic components

from systems.qora.gcb.builder import build_gcb, dispatch_gcb_to_simula
from systems.qora.manifest.builder import build_manifest

# REFACTORED: Define Pydantic models for the request body
# --------------------------------------------------------
class GcbTarget(BaseModel):
    """
    Represents a single target object. Allows any structure within the object
    to maintain flexibility while ensuring it's a valid dictionary.
    """
    class Config:
        extra = "allow"

class GcbRequest(BaseModel):
    """Defines the request body for the /build and /dispatch endpoints."""
    targets: list[GcbTarget] = Field(default_factory=list)
# --------------------------------------------------------

gcb_router = APIRouter(tags=["qora.gcb"])


@gcb_router.post("/build")
def build(
    # REFACTORED: Accept the Pydantic model for the request body
    req: GcbRequest,
    decision_id: str = Query(...),
    system: str = Query(...),
    code_root: str = Query("./"),
) -> dict:
    """
    Build a deterministic manifest for `system` by scanning `code_root`.
    """
    m = build_manifest(system, code_root)
    # REFACTORED: Convert Pydantic models to dicts for the internal function call
    targets_dict = [t.model_dump() for t in req.targets]
    gcb = build_gcb(decision_id, {"system": system}, targets_dict, m)
    return {"gcb": gcb.model_dump()}


@gcb_router.post("/dispatch")
def dispatch(
    # REFACTORED: Accept the Pydantic model for the request body
    req: GcbRequest,
    decision_id: str = Query(...),
    system: str = Query(...),
    code_root: str = Query("./"),
) -> dict:
    """
    Build a GCB and send it to Simula via SIMULA_JOBS_CODEGEN.
    Contract obeyed: {"spec": <GCB JSON>, "targets": [...]}.
    """
    m = build_manifest(system, code_root)
    # REFACTORED: Convert Pydantic models to dicts for the internal function call
    targets_dict = [t.model_dump() for t in req.targets]
    gcb = build_gcb(decision_id, {"system": system}, targets_dict, m)
    result = dispatch_gcb_to_simula(gcb)
    return {"submitted": True, "result": result, "gcb_hash": gcb.model_dump_json()[:64]}