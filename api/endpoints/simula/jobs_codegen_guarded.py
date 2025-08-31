# api/endpoints/simula/jobs_codegen_guarded.py
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from httpx import AsyncClient
from pydantic import BaseModel, Field

from core.utils.net_api import ENDPOINTS, get_http_client

router = APIRouter()
log = logging.getLogger("simula.api.codegen_guarded")

# ---------- Models ----------

class GuardedTarget(BaseModel):
    additionalProp1: dict[str, Any] = Field(default_factory=dict)

class GuardedCodegenReq(BaseModel):
    spec: str
    diff: str
    budget_ms: int = 0
    targets: list[GuardedTarget] = Field(default_factory=list)

class GuardedCodegenResp(BaseModel):
    policy_result: dict[str, Any] | None = None
    forwarded_to_codegen: bool = False
    codegen_response: dict[str, Any] | None = None

# ---------- Route ----------

@router.post("/jobs/codegen_guarded", response_model=GuardedCodegenResp)
async def jobs_codegen_guarded(
    payload: GuardedCodegenReq,                                   # ✅ Pydantic model (not a function)
    x_decision_id: str | None = Header(default=None, alias="x-decision-id"),  # ✅ Header(...)
    http_client: AsyncClient = Depends(get_http_client),           # ✅ Depends(get_http_client)
) -> GuardedCodegenResp:
    """
    Example flow:
      1) (Optional) call Equor policy validate
      2) If OK, forward to /simula/jobs/codegen
    """
    # 1) OPTIONAL POLICY CHECK (skip if you don't have this endpoint)
    policy_url = getattr(ENDPOINTS, "EQUOR_POLICY_VALIDATE", "/equor/policy/validate")
    try:
        policy_res = await http_client.post(policy_url, json={"diff": payload.diff})
        if policy_res.status_code == 404:
            # no policy service → treat as pass-through
            policy_result = {"skipped": True}
        else:
            policy_res.raise_for_status()
            policy_result = policy_res.json() or {}
    except Exception as e:
        log.warning("policy validate failed (continuing open): %r", e)
        policy_result = {"error": repr(e)}

    # 2) FORWARD TO CODEGEN
    try:
        forward_body = {
            "spec": payload.spec,
            "targets": [t.model_dump() for t in payload.targets],
            "budget_ms": payload.budget_ms,
        }
        res = await http_client.post(ENDPOINTS.SIMULA_JOBS_CODEGEN, json=forward_body, headers={
            "x-decision-id": x_decision_id or "",
        })
        res.raise_for_status()
        return GuardedCodegenResp(
            policy_result=policy_result,
            forwarded_to_codegen=True,
            codegen_response=res.json() or {},
        )
    except Exception as e:
        log.error("forward to codegen failed: %r", e)
        raise HTTPException(status_code=502, detail=f"Codegen service failed: {e!r}")
