from __future__ import annotations

from fastapi import APIRouter, Query

from systems.qora.manifest.builder import build_manifest

manifest_router = APIRouter(tags=["manifest"])


@manifest_router.post("/build")
def build(
    system: str = Query(..., description="System name"),
    code_root: str = Query("./"),
) -> dict:
    """
    Build a deterministic manifest for `system` by scanning `code_root`.
    """
    m = build_manifest(system, code_root)
    return {"manifest": m.model_dump()}


@manifest_router.get("/latest")
def latest(system: str = Query(...), code_root: str = Query("./")) -> dict:
    """
    For now, mirrors /build. Wire to your store if you persist manifests.
    """
    m = build_manifest(system, code_root)
    return {"manifest": m.model_dump()}
