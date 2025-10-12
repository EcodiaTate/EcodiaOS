from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

policy_packs_router = APIRouter(prefix="/policy/packs", tags=["policy"])

try:
    from systems.qora.policy.packs import list_packs, read_pack, write_pack
except Exception:  # pragma: no cover
    list_packs = None
    write_pack = None
    read_pack = None


class PackFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    content: str


class PackUpload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1)
    files: list[PackFile] = Field(default_factory=list)


@policy_packs_router.get("/")
async def packs_list() -> dict[str, Any]:
    if not list_packs:
        raise HTTPException(status_code=501, detail="policy packs store unavailable")
    try:
        packs = list_packs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"list failed: {e!r}")
    return {"packs": packs}


@policy_packs_router.post("/upload")
async def packs_upload(req: PackUpload) -> dict[str, Any]:
    if not write_pack:
        raise HTTPException(status_code=501, detail="policy packs store unavailable")
    try:
        files = [f.model_dump() for f in req.files]
        write_pack(req.name, files)
        return {"ok": True, "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"upload failed: {e!r}")


@policy_packs_router.get("/{name}")
async def packs_get(name: str) -> dict[str, Any]:
    if not read_pack:
        raise HTTPException(status_code=501, detail="policy packs store unavailable")
    try:
        data = read_pack(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read failed: {e!r}")
    if not data:
        raise HTTPException(status_code=404, detail="pack not found")
    return {"name": name, **data}
