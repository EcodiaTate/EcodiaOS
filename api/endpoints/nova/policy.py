# file: api/endpoints/nova/policy.py
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel

from systems.nova.clients.equor_client import EquorPolicyClient

router = APIRouter(tags=["nova-policy"])
_eq = EquorPolicyClient()


def _stamp_cost(res: Response, t0: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - t0) * 1000))


class PolicyCheckRequest(BaseModel):
    capability_spec: dict[str, Any] = {}
    obligations: dict[str, Any] = {}
    identity_context: dict[str, Any] = {}


@router.post("/policy/validate", response_model=dict[str, Any])
async def policy_validate(req: PolicyCheckRequest, response: Response) -> dict[str, Any]:
    t0 = time.perf_counter()
    out = await _eq.validate(req.dict())

    # Minimal, non-breaking telemetry headers
    # Publish whether Equor accepted the policy and echo a lightweight reason if provided
    try:
        ok = bool(out.get("ok", False))
        response.headers["X-Equor-OK"] = "true" if ok else "false"
        reason = out.get("reason") or out.get("stage") or ""
        if reason:
            response.headers["X-Equor-Reason"] = str(reason)[:128]
    except Exception:
        pass

    _stamp_cost(response, t0)
    return out
