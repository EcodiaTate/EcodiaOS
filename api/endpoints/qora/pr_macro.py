from __future__ import annotations

import os
import shlex
import subprocess
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    REPO = str(getattr(settings, "repo_root", os.getcwd()))
except Exception:
    REPO = os.getcwd()


def _run(cmd: list[str], input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, capture_output=True, input=input_bytes)


def _git(*args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return _run(["git", *args], input_bytes=input_bytes)


class PRMacroRequest(BaseModel):
    diff: str = Field(..., description="Unified diff to apply")
    branch_base: str = Field("main")
    branch_name: str | None = None
    commit_message: str = Field("Apply Simula/Qora proposal")
    remote: str = Field("origin")
    pr_title: str = Field("Simula/Qora proposal")
    pr_body_markdown: str = Field("", description="Optional PR body")


class PRMacroResponse(BaseModel):
    ok: bool
    branch: str
    commit: str | None = None
    pr_url_hint: str = ""


@router.post("/git/pr_macro", response_model=PRMacroResponse)
async def pr_macro(req: PRMacroRequest) -> PRMacroResponse:
    if not os.path.isdir(os.path.join(REPO, ".git")):
        raise HTTPException(status_code=400, detail=f"Not a git repo: {REPO}")

    # 1) branch
    name = req.branch_name or f"simula/{int(time.time())}"
    cp = _git("checkout", "-B", name, req.branch_base)
    if cp.returncode != 0:
        raise HTTPException(status_code=400, detail=cp.stderr.decode() or cp.stdout.decode())

    # 2) apply diff + index
    cp = _git(
        "apply",
        "--index",
        "--whitespace=fix",
        "-p0",
        input_bytes=req.diff.encode("utf-8", "replace"),
    )
    if cp.returncode != 0:
        # fallback without index
        cp2 = _git(
            "apply",
            "--whitespace=fix",
            "-p0",
            input_bytes=req.diff.encode("utf-8", "replace"),
        )
        if cp2.returncode != 0:
            raise HTTPException(status_code=400, detail=cp.stderr.decode() or cp.stdout.decode())

    # 3) commit
    _ = _git("add", "-A")
    cp = _git("commit", "-m", req.commit_message)
    sha = None
    if cp.returncode == 0:
        show = _git("rev-parse", "--short", "HEAD")
        sha = show.stdout.decode().strip() if show.returncode == 0 else None

    # 4) push
    cp = _git("push", req.remote, name)
    if cp.returncode != 0:
        raise HTTPException(status_code=400, detail=cp.stderr.decode() or cp.stdout.decode())

    # 5) PR URL hint (gh optional)
    url = (_git("config", f"remote.{req.remote}.url").stdout.decode() or "").strip()
    hint = "(open PR manually)"
    if "github.com" in url:
        path = url.split("github.com")[-1].lstrip(":").lstrip("/").removesuffix(".git")
        hint = f"https://github.com/{path}/compare/{req.branch_base}...{name}?expand=1"
        # try gh
        gh = _run(["bash", "-lc", "command -v gh >/dev/null 2>&1 && echo yes || echo no"])
        if gh.stdout.decode().strip() == "yes":
            cmd = f"gh pr create --title {shlex.quote(req.pr_title)} --body {shlex.quote(req.pr_body_markdown or '')} --base {shlex.quote(req.branch_base)} --head {shlex.quote(name)} --repo {url}"
            cp = _run(["bash", "-lc", cmd])
            if cp.returncode == 0:
                hint = (cp.stdout.decode() or hint).strip()
    return PRMacroResponse(ok=True, branch=name, commit=sha, pr_url_hint=hint)
