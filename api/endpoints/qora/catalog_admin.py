from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

catalog_admin_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    ART = Path(getattr(settings, "artifacts_root", ".simula")).resolve()
except Exception:  # pragma: no cover
    ART = Path(".simula").resolve()

REG_DIR = ART / "catalog"
REG_FILE = REG_DIR / "tools_catalog.json"


def _load() -> dict[str, Any]:
    if REG_FILE.exists():
        try:
            return json.loads(REG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tools": {}, "retired": {}}


def _save(data: dict[str, Any]) -> None:
    REG_DIR.mkdir(parents=True, exist_ok=True)
    REG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    returns: dict[str, Any] = Field(default_factory=dict)
    safety: int = 1
    tags: list[str] = Field(default_factory=list)
    endpoint_hint: str | None = None  # optional pointer to http endpoint


class RegisterReq(BaseModel):
    spec: ToolSpec


class RetireReq(BaseModel):
    name: str
    reason: str = ""


@catalog_admin_router.get("/list")
async def catalog_list() -> dict[str, Any]:
    data = _load()
    return {
        "ok": True,
        "tools": list(data["tools"].values()),
        "retired": list(data["retired"].values()),
    }


@catalog_admin_router.get("/get")
async def catalog_get(name: str) -> dict[str, Any]:
    data = _load()
    if name in data["tools"]:
        return {"ok": True, "tool": data["tools"][name]}
    if name in data["retired"]:
        return {"ok": True, "tool": data["retired"][name], "retired": True}
    raise HTTPException(status_code=404, detail="tool not found")


@catalog_admin_router.post("/register")
async def catalog_register(req: RegisterReq) -> dict[str, Any]:
    data = _load()
    spec = req.spec.dict()
    spec["updated_at"] = int(time.time())
    data["tools"][spec["name"]] = spec
    if spec["name"] in data["retired"]:
        data["retired"].pop(spec["name"], None)
    _save(data)
    return {"ok": True, "tool": spec}


@catalog_admin_router.post("/retire")
async def catalog_retire(req: RetireReq) -> dict[str, Any]:
    data = _load()
    if req.name not in data["tools"]:
        raise HTTPException(status_code=404, detail="tool not active")
    spec = data["tools"].pop(req.name)
    spec["retired_at"] = int(time.time())
    spec["retire_reason"] = req.reason
    data["retired"][req.name] = spec
    _save(data)
    return {"ok": True, "tool": spec}
