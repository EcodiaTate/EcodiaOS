from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], timeout: int = 1800) -> dict[str, Any]:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"rc": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "stdout": "", "stderr": "timeout"}


class MutReq(BaseModel):
    paths: list[str] = Field(default_factory=lambda: ["."], description="Target modules/paths")
    tests: list[str] = Field(default_factory=lambda: ["tests"], description="Test dirs")
    timeout_sec: int = Field(1800, ge=300, le=7200)


class MutResp(BaseModel):
    ok: bool
    killed: int = 0
    survived: int = 0
    timeout: int = 0
    suspicious: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


@router.post("/mutation/run", response_model=MutResp)
async def mutation_run(req: MutReq) -> MutResp:
    if not _have("mutmut"):
        return MutResp(ok=False, note="mutmut not installed")
    cmd = [
        "mutmut",
        "run",
        "--paths-to-mutate",
        ",".join(req.paths),
        "--tests-dir",
        ",".join(req.tests),
        "--json",
    ]
    out = _run(cmd, timeout=req.timeout_sec)
    try:
        j = json.loads(out["stdout"] or "{}")
        return MutResp(
            ok=True,
            killed=j.get("killed", 0),
            survived=j.get("survived", 0),
            timeout=j.get("timeout", 0),
            suspicious=j.get("suspicious", 0),
            raw=j,
        )
    except Exception:
        return MutResp(
            ok=False,
            note="failed to parse mutmut json",
            raw={"stdout": out["stdout"], "stderr": out["stderr"]},
        )
