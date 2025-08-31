from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

safety_router = APIRouter()


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], timeout: int = 120, cwd: str | None = None) -> dict[str, Any]:
    try:
        cp = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, text=True)
        return {"rc": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "stdout": "", "stderr": "timeout"}


class SafetyScanRequest(BaseModel):
    paths: list[str] = Field(default_factory=lambda: ["."], description="Paths (repo-relative)")
    run_bandit: bool = True
    run_semgrep: bool = True
    run_pip_audit: bool = True
    semgrep_config: str = Field("auto", description="semgrep config (e.g. 'p/ci' or 'auto')")
    timeout_sec: int = Field(300, ge=30, le=3600)


class SafetyScanResponse(BaseModel):
    ok: bool
    tools: dict[str, Any] = Field(default_factory=dict)


@safety_router.post("/scan", response_model=SafetyScanResponse)
async def safety_scan(req: SafetyScanRequest) -> SafetyScanResponse:
    tools: dict[str, Any] = {}

    # ---- bandit (python) ----
    if req.run_bandit:
        if not _have("bandit"):
            tools["bandit"] = {"available": False, "note": "bandit not installed"}
        else:
            cmd = ["bandit", "-q", "-f", "json", "-r", *req.paths]
            out = _run(cmd, timeout=min(180, req.timeout_sec))
            try:
                payload = json.loads(out["stdout"] or "{}")
            except Exception:
                payload = {"raw": out}
            tools["bandit"] = {"available": True, "rc": out["rc"], "report": payload}

    # ---- semgrep ----
    if req.run_semgrep:
        if not _have("semgrep"):
            tools["semgrep"] = {"available": False, "note": "semgrep not installed"}
        else:
            cfg = req.semgrep_config or "auto"
            cmd = ["semgrep", "--error", "--json", "--quiet", "--config", cfg, *req.paths]
            out = _run(cmd, timeout=min(240, req.timeout_sec))
            try:
                payload = json.loads(out["stdout"] or "{}")
            except Exception:
                payload = {"raw": out}
            tools["semgrep"] = {"available": True, "rc": out["rc"], "report": payload}

    # ---- pip-audit (dependencies) ----
    if req.run_pip_audit:
        if not _have("pip-audit"):
            tools["pip_audit"] = {"available": False, "note": "pip-audit not installed"}
        else:
            audit: dict[str, Any] = {"available": True, "runs": []}
            # Try common requirement files
            candidates = [
                "requirements.txt",
                "requirements-prod.txt",
                "requirements.lock",
                "pyproject.toml",
            ]
            for f in candidates:
                if os.path.isfile(f):
                    args = ["pip-audit", "-r", f, "-f", "json"]
                    out = _run(args, timeout=min(180, req.timeout_sec))
                    try:
                        payload = json.loads(out["stdout"] or "[]")
                    except Exception:
                        payload = {"raw": out}
                    audit["runs"].append({"file": f, "rc": out["rc"], "report": payload})
            if not audit["runs"]:
                audit["note"] = "no requirements file found"
            tools["pip_audit"] = audit

    return SafetyScanResponse(ok=True, tools=tools)
