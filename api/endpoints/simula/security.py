# ===== FILE: api/endpoints/simula/security.py =====
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from systems.simula.agent import qora_adapters as _qora
from systems.simula.config import settings

router = APIRouter(tags=["simula"])


class SecretsReq(BaseModel):
    model_config = ConfigDict(extra="ignore")
    paths: list[str] | None = Field(default=None, description="Specific repo-relative paths to scan")
    use_heavy: bool = Field(default=True, description="Enable heavier/ML checks if available")
    limit: int = Field(default=5000, ge=1, le=100000)


class HygieneReq(BaseModel):
    model_config = ConfigDict(extra="ignore")
    diff: str
    auto_heal: bool = True
    timeout_sec: int = Field(default=900, ge=60, le=7200)


assert isinstance(SecretsReq, type) and issubclass(SecretsReq, BaseModel)
assert isinstance(HygieneReq, type) and issubclass(HygieneReq, BaseModel)


@router.post("/security/secrets-scan")
async def secrets_scan(req: SecretsReq) -> dict[str, Any]:
    res = await _qora.qora_secrets_scan(paths=req.paths, use_heavy=req.use_heavy, limit=req.limit)
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("reason", "scan failed"))
    return {"status": "success", "result": res.get("result")}


@router.post("/security/hygiene")
async def hygiene(req: HygieneReq) -> dict[str, Any]:
    res = await _qora.qora_hygiene_check(
        diff=req.diff,
        auto_heal=req.auto_heal and settings.gates.run_safety,
        timeout_sec=req.timeout_sec,
    )
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("reason", "hygiene failed"))
    return {"status": "success", "result": res.get("result")}
