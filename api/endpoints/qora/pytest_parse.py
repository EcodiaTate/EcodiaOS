from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

pytest_parse_router = APIRouter()

try:
    from systems.simula.code_sim.diagnostics.error_parser import parse_pytest_output  # type: ignore
except Exception:  # pragma: no cover
    parse_pytest_output = None


class ParseReq(BaseModel):
    stdout: str = Field("", description="pytest stdout/stderr blob")


@pytest_parse_router.post("/pytest/parse", response_model=dict[str, Any])
async def parse(req: ParseReq) -> dict[str, Any]:
    if not callable(parse_pytest_output):
        return {"ok": False, "reason": "parser unavailable"}
    try:
        fails = [f.__dict__ for f in parse_pytest_output(req.stdout or "")]
        return {"ok": True, "failures": fails}
    except Exception as e:
        return {"ok": False, "reason": repr(e)}
