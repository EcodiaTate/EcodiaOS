from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

bb_router = APIRouter()

# minimal in-proc kv with durability via Simula artifacts store
try:
    from systems.qora.storage import load_json, save_json  # type: ignore
except Exception:  # pragma: no cover
    load_json = save_json = None


class BBWrite(BaseModel):
    key: str = Field(..., min_length=1)
    value: Any


@bb_router.post("/write")
async def bb_write(req: BBWrite) -> dict[str, Any]:
    if not callable(load_json) or not callable(save_json):
        raise HTTPException(status_code=501, detail="blackboard store unavailable")
    db = load_json("blackboard.json", {})
    db[req.key] = req.value
    save_json("blackboard.json", db)
    return {"ok": True}


@bb_router.get("/read")
async def bb_read(key: str) -> dict[str, Any]:
    if not callable(load_json):
        raise HTTPException(status_code=501, detail="blackboard store unavailable")
    db = load_json("blackboard.json", {})
    return {"value": db.get(key)}
