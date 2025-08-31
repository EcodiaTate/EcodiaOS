# api/endpoints/qora/arch_exec.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from systems.qora.core.architecture.arch_execution import (
    arch_execute_by_uid,
    arch_fetch_schema,
    arch_search,
)

arch_exec_router = APIRouter()


class SearchReq(BaseModel):
    query: str = Field(..., description="Natural language capability query")
    top_k: int = 5
    safety_max: int | None = 2
    system: str | None = None


class ExecByUidReq(BaseModel):
    uid: str
    args: dict[str, Any] = {}
    caller: str | None = None
    log: bool = True


class ExecByQueryReq(BaseModel):
    query: str
    args: dict[str, Any] = {}
    caller: str | None = None
    top_k: int = 3
    safety_max: int | None = 2
    system: str | None = None
    log: bool = True


@arch_exec_router.post("/search")
async def api_search(req: SearchReq, x_qora_key: str | None = Header(None)):
    # lightweight key check (optionally enforce stronger auth in deps)
    if not x_qora_key:
        raise HTTPException(status_code=401, detail="Missing X-Qora-Key")
    res = await arch_search(req.query, req.top_k, req.safety_max, req.system)
    return {"ok": True, "candidates": res}


@arch_exec_router.get("/schema/{uid}")
async def api_schema(uid: str, x_qora_key: str | None = Header(None)):
    if not x_qora_key:
        raise HTTPException(status_code=401, detail="Missing X-Qora-Key")
    sch = await arch_fetch_schema(uid)
    if not sch:
        raise HTTPException(status_code=404, detail="No schema")
    return sch


@arch_exec_router.post("/execute-by-uid")
async def api_exec_uid(req: ExecByUidReq, x_qora_key: str | None = Header(None)):
    if not x_qora_key:
        raise HTTPException(status_code=401, detail="Missing X-Qora-Key")
    ok, data = await arch_execute_by_uid(req.uid, req.args, req.caller, req.log)
    if not ok:
        raise HTTPException(status_code=400, detail=data.get("error", "Execution failed"))
    return {"ok": True, **data}


@arch_exec_router.post("/execute-by-query")
async def api_exec_query(req: ExecByQueryReq, x_qora_key: str | None = Header(None)):
    if not x_qora_key:
        raise HTTPException(status_code=401, detail="Missing X-Qora-Key")
    cands = await arch_search(req.query, req.top_k, req.safety_max, req.system)
    if not cands:
        return {"ok": False, "error": "No candidates"}
    uid = cands[0]["uid"]
    ok, data = await arch_execute_by_uid(uid, req.args, req.caller, req.log)
    if not ok:
        return {"ok": False, **data}
    return {"ok": True, "candidate": cands[0], **data}
