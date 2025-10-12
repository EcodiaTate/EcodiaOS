# systems/qora/service/wm_router.py
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from systems.qora.service.schemas import (
    BbReadResponse,
    DossierResponse,
    SubgraphResponse,
)
from systems.qora.service.schemas import (
    BbWrite as _BbWrite,
)
from systems.qora.service.schemas import (
    DossierRequest as _DossierRequest,
)
from systems.qora.service.schemas import (
    IndexFileRequest as _IndexFileRequest,
)

# Reuse your in-repo WM layer
from systems.qora.wm.service import DossierBuilder, WMIndex, WMService  # type: ignore

router = APIRouter(prefix="/qora/wm", tags=["qora-wm"])

# -------------------------------------------------------------------
# Safe local shims for request models (Pydantic v2 tolerant)
# -------------------------------------------------------------------

try:
    if isinstance(_DossierRequest, type) and issubclass(_DossierRequest, BaseModel):

        class DossierRequest(_DossierRequest):  # type: ignore[misc, valid-type]
            model_config = ConfigDict(extra="ignore")
    else:

        class DossierRequest(BaseModel):
            model_config = ConfigDict(extra="ignore")
            target_fqname: str
            intent: str | None = None
except Exception:

    class DossierRequest(BaseModel):
        model_config = ConfigDict(extra="ignore")
        target_fqname: str
        intent: str | None = None


try:
    if isinstance(_BbWrite, type) and issubclass(_BbWrite, BaseModel):

        class BbWrite(_BbWrite):  # type: ignore[misc, valid-type]
            model_config = ConfigDict(extra="ignore")
    else:

        class BbWrite(BaseModel):
            model_config = ConfigDict(extra="ignore")
            key: str
            value: Any
except Exception:

    class BbWrite(BaseModel):
        model_config = ConfigDict(extra="ignore")
        key: str
        value: Any


try:
    if isinstance(_IndexFileRequest, type) and issubclass(_IndexFileRequest, BaseModel):

        class IndexFileRequest(_IndexFileRequest):  # type: ignore[misc, valid-type]
            model_config = ConfigDict(extra="ignore")
    else:

        class IndexFileRequest(BaseModel):
            model_config = ConfigDict(extra="ignore")
            path: str = Field(..., description="Filesystem path of the source file")
except Exception:

    class IndexFileRequest(BaseModel):
        model_config = ConfigDict(extra="ignore")
        path: str = Field(..., description="Filesystem path of the source file")


@router.post("/dossier", response_model=DossierResponse)
async def build_dossier(req: DossierRequest) -> DossierResponse:
    try:
        data: dict[str, Any] = DossierBuilder.dossier(req.target_fqname, intent=req.intent)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"dossier failed: {e!r}")
    # normalize a little into the response model
    return DossierResponse(
        target_fqname=req.target_fqname,
        intent=req.intent,
        summary=data.get("summary") or "",
        files=data.get("files") or [],
        symbols=data.get("symbols") or [],
        related=data.get("related") or [],
        meta={k: v for k, v in data.items() if k not in {"summary", "files", "symbols", "related"}},
    )


@router.get("/graph/subgraph", response_model=SubgraphResponse)
async def subgraph(
    fqname: str = Query(...),
    hops: int = Query(1, ge=0, le=3),  # reserved for future expansion
) -> SubgraphResponse:
    """
    Lightweight, file-level relatedness subgraph:
    - Node 0: the requested file
    - Related files: share any import with Node 0 (based on WMIndex)
    """
    file_path = fqname.split("::", 1)[0]
    if not os.path.exists(file_path):
        return SubgraphResponse(nodes=[], edges=[])

    base_imports: list[str] = (getattr(WMIndex, "imports", None) or {}).get(file_path, [])
    nodes = [{"id": file_path, "type": "file", "role": "target"}]
    edges: list[dict[str, Any]] = []
    seen = {file_path}

    for other, imps in (getattr(WMIndex, "imports", None) or {}).items():
        if other == file_path:
            continue
        if not imps:
            continue
        if set(imps).intersection(base_imports) and other not in seen:
            nodes.append({"id": other, "type": "file", "role": "related"})
            edges.append({"src": file_path, "dst": other, "kind": "shared_import"})
            seen.add(other)
            if len(nodes) >= 64:
                break

    return SubgraphResponse(nodes=nodes, edges=edges)


@router.post("/bb/write", response_model=dict[str, Any])
async def bb_write(req: BbWrite) -> dict[str, Any]:
    try:
        WMService.bb_write(req.key, req.value)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"bb_write failed: {e!r}")


@router.get("/bb/read", response_model=BbReadResponse)
async def bb_read(key: str = Query(...)) -> BbReadResponse:
    try:
        val = WMService.bb_read(key)
        return BbReadResponse(key=key, value=val)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"bb_read failed: {e!r}")


@router.post("/index_file", response_model=dict[str, Any])
async def index_file(req: IndexFileRequest) -> dict[str, Any]:
    try:
        ok = WMService.index_file(req.path)
        return {"ok": bool(ok)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"index_file failed: {e!r}")
