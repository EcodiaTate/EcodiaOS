from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    REPO = Path(getattr(settings, "repo_root", ".")).resolve()
except Exception:  # pragma: no cover
    REPO = Path(".").resolve()


def _run(args: list[str]) -> dict[str, Any]:
    cp = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return {"rc": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}


class RollbackReq(BaseModel):
    action: str = Field(..., description="one of: revert, reset, delete_branch, restore_ref")
    commit_sha: str | None = None  # for revert/restore_ref
    branch: str | None = None  # for reset/delete_branch
    to_ref: str | None = None  # for reset (e.g., origin/main or SHA)
    dry_run: bool = True
    push: bool = False
    remote: str = "origin"


class RollbackResp(BaseModel):
    ok: bool
    action: str
    cmds: list[str] = Field(default_factory=list)
    log: dict[str, Any] = Field(default_factory=dict)


@router.post("/git/rollback", response_model=RollbackResp)
async def git_rollback(req: RollbackReq) -> RollbackResp:
    cmds: list[str] = []
    log: dict[str, Any] = {}

    if req.action == "revert":
        if not req.commit_sha:
            raise HTTPException(400, "commit_sha required")
        cmds = [f"git revert --no-edit {req.commit_sha}"]
        if not req.dry_run:
            r1 = _run(["revert", "--no-edit", req.commit_sha])
            log["revert"] = r1
            if r1["rc"] != 0:
                return RollbackResp(ok=False, action=req.action, cmds=cmds, log=log)
            if req.push:
                log["push"] = _run(["push", req.remote, "HEAD"])

    elif req.action == "reset":
        if not (req.branch and req.to_ref):
            raise HTTPException(400, "branch and to_ref required")
        cmds = [f"git checkout {req.branch}", f"git reset --hard {req.to_ref}"]
        if not req.dry_run:
            c1 = _run(["checkout", req.branch])
            log["checkout"] = c1
            if c1["rc"] != 0:
                return RollbackResp(ok=False, action=req.action, cmds=cmds, log=log)
            c2 = _run(["reset", "--hard", req.to_ref])
            log["reset"] = c2
            if c2["rc"] != 0:
                return RollbackResp(ok=False, action=req.action, cmds=cmds, log=log)
            if req.push:
                log["push"] = _run(["push", "-f", req.remote, req.branch])

    elif req.action == "delete_branch":
        if not req.branch:
            raise HTTPException(400, "branch required")
        cmds = [f"git branch -D {req.branch}"]
        if not req.dry_run:
            d = _run(["branch", "-D", req.branch])
            log["delete"] = d
            if req.push:
                log["push_delete"] = _run(["push", req.remote, f":{req.branch}"])

    elif req.action == "restore_ref":
        if not req.commit_sha:
            raise HTTPException(400, "commit_sha required")
        branch = req.branch or f"restore/{req.commit_sha[:8]}"
        cmds = [f"git checkout -b {branch} {req.commit_sha}"]
        if not req.dry_run:
            c = _run(["checkout", "-b", branch, req.commit_sha])
            log["checkout"] = c
            if c["rc"] != 0:
                return RollbackResp(ok=False, action=req.action, cmds=cmds, log=log)
            if req.push:
                log["push"] = _run(["push", req.remote, branch])
    else:
        raise HTTPException(400, "unsupported action")

    return RollbackResp(ok=True, action=req.action, cmds=cmds, log=log)
