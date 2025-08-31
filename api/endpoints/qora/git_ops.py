from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

git_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    REPO = Path(getattr(settings, "repo_root", ".")).resolve()
except Exception:  # pragma: no cover
    REPO = Path(".").resolve()


def _run(args: list[str]) -> dict[str, Any]:
    cp = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    return {"rc": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr, "cmd": " ".join(args)}


def _git(args: list[str]) -> dict[str, Any]:
    return _run(["git", *args])


# ----------------------------- Schemas -------------------------------------


class BranchFromDiffReq(BaseModel):
    diff: str
    branch: str
    base_ref: str = "origin/main"
    commit_msg: str = "Simula change"


class BranchFromDiffResp(BaseModel):
    ok: bool
    branch: str | None = None
    logs: dict[str, Any] = Field(default_factory=dict)


class PrOpenReq(BaseModel):
    title: str
    head: str
    body: str = "Automated PR from Qora."
    base: str = "main"
    draft: bool = False
    labels: list[str] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)


class PrOpenResp(BaseModel):
    ok: bool
    url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


# ------------------------------ Routes -------------------------------------


@git_router.post("/branch_from_diff", response_model=BranchFromDiffResp)
async def branch_from_diff(req: BranchFromDiffReq) -> BranchFromDiffResp:
    _ = _git(["fetch", "--all", "--prune"])
    c1 = _git(["checkout", "-b", req.branch, req.base_ref])
    if c1["rc"] != 0:
        return BranchFromDiffResp(ok=False, logs={"checkout": c1})

    # apply diff (prefer staged apply; fallback to working tree)
    ap = _run(["git", "apply", "--index", "--whitespace=fix", "-p0"])
    if ap["rc"] != 0:
        ap2 = _run(["git", "apply", "--whitespace=fix", "-p0"])
        if ap2["rc"] != 0:
            return BranchFromDiffResp(ok=False, logs={"apply1": ap, "apply2": ap2})

    cm = _git(["commit", "-m", req.commit_msg])
    if cm["rc"] != 0:
        return BranchFromDiffResp(ok=False, logs={"commit": cm})

    ps = _git(["push", "-u", "origin", req.branch])
    if ps["rc"] != 0:
        return BranchFromDiffResp(ok=False, logs={"push": ps})

    return BranchFromDiffResp(
        ok=True,
        branch=req.branch,
        logs={"checkout": c1, "apply": ap, "commit": cm, "push": ps},
    )


@git_router.post("/gh_open_pr", response_model=PrOpenResp)
async def gh_open_pr(req: PrOpenReq) -> PrOpenResp:
    # Prefer GitHub CLI if present; otherwise advise to use auto_pipeline with GH_TOKEN in env.
    if subprocess.run(["which", "gh"], capture_output=True).returncode == 0:
        args = [
            "gh",
            "pr",
            "create",
            "--title",
            req.title,
            "--body",
            req.body,
            "--base",
            req.base,
            "--head",
            req.head,
        ]
        if req.draft:
            args.append("--draft")
        for lb in req.labels:
            args += ["--label", lb]
        r = _run(args)
        if r["rc"] == 0 and "https://" in r["stdout"]:
            m = re.search(r"(https://\S+)", r["stdout"])
            return PrOpenResp(ok=True, url=m.group(1) if m else None, raw=r)
        return PrOpenResp(ok=False, raw=r, note="gh cli failed")
    else:
        return PrOpenResp(
            ok=False,
            note="Install gh CLI or use /qora/auto/pipeline with GH_TOKEN/GITHUB_TOKEN.",
        )


import os
import subprocess

try:
    from systems.simula.config import settings  # type: ignore

    REPO = str(getattr(settings, "repo_root", os.getcwd()))
except Exception:  # pragma: no cover
    REPO = os.getcwd()


# ---------------- models ----------------
class BranchRequest(BaseModel):
    base: str = Field(default="HEAD", description="Base ref to branch from (e.g., main)")
    name: str = Field(..., min_length=2, description="New branch name")


class BranchResponse(BaseModel):
    ok: bool
    branch: str
    base: str


class ApplyDiffRequest(BaseModel):
    diff: str = Field(..., description="Unified diff")
    index: bool = Field(True, description="Add to index after apply")
    whitespace_fix: bool = Field(True, description="Fix whitespace on apply")


class ApplyDiffResponse(BaseModel):
    ok: bool
    applied: bool
    message: str


class CommitRequest(BaseModel):
    message: str = Field(..., min_length=3)
    add_all: bool = Field(True)


class CommitResponse(BaseModel):
    ok: bool
    commit: str | None = None
    message: str = ""


class PushRequest(BaseModel):
    remote: str = Field("origin")
    branch: str = Field(...)


class PushResponse(BaseModel):
    ok: bool
    remote: str
    branch: str
    message: str = ""


class PRPrepareRequest(BaseModel):
    remote: str = Field("origin")
    branch: str = Field(...)
    base: str = Field("main")
    title: str = Field("Simula/Qora proposal")
    body_markdown: str = Field("", description="Optional PR body")


class PRPrepareResponse(BaseModel):
    ok: bool
    url_hint: str
    message: str = ""


# ---------------- helpers ----------------
def _run(cmd: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, input=input_bytes, capture_output=True)


def _git(*args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return _run(["git", *args], input_bytes=input_bytes)


def _ensure_repo() -> None:
    if not os.path.isdir(os.path.join(REPO, ".git")):
        raise HTTPException(status_code=400, detail=f"Not a git repo: {REPO}")


# ---------------- endpoints ----------------
@git_router.post("/branch", response_model=BranchResponse)
async def git_branch(req: BranchRequest) -> BranchResponse:
    _ensure_repo()
    cp = _git("checkout", "-B", req.name, req.base)
    if cp.returncode != 0:
        raise HTTPException(status_code=400, detail=cp.stderr.decode() or cp.stdout.decode())
    return BranchResponse(ok=True, branch=req.name, base=req.base)


@git_router.post("/apply_diff", response_model=ApplyDiffResponse)
async def git_apply_diff(req: ApplyDiffRequest) -> ApplyDiffResponse:
    _ensure_repo()
    args = ["apply"]
    if req.index:
        args.append("--index")
    if req.whitespace_fix:
        args.append("--whitespace=fix")
    # Use -p0 so unified diffs with a/ b/ work normally
    args.append("-p0")
    cp = _git(*args, input_bytes=req.diff.encode("utf-8", "replace"))
    if cp.returncode != 0:
        # Try without --index as a fallback
        if req.index:
            cp2 = _git(
                "apply",
                "--whitespace=fix",
                "-p0",
                input_bytes=req.diff.encode("utf-8", "replace"),
            )
            if cp2.returncode == 0:
                return ApplyDiffResponse(ok=True, applied=True, message="Applied without indexing")
        raise HTTPException(status_code=400, detail=cp.stderr.decode() or cp.stdout.decode())
    return ApplyDiffResponse(ok=True, applied=True, message="Applied")


@git_router.post("/commit", response_model=CommitResponse)
async def git_commit(req: CommitRequest) -> CommitResponse:
    _ensure_repo()
    if req.add_all:
        cp_add = _git("add", "-A")
        if cp_add.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=cp_add.stderr.decode() or cp_add.stdout.decode(),
            )
    cp = _git("commit", "-m", req.message)
    if cp.returncode != 0:
        out = (cp.stderr.decode() or cp.stdout.decode()).strip()
        if "nothing to commit" in out.lower():
            return CommitResponse(ok=True, commit=None, message="Nothing to commit")
        raise HTTPException(status_code=400, detail=out)
    # parse short sha
    show = _git("rev-parse", "--short", "HEAD")
    sha = show.stdout.decode().strip() if show.returncode == 0 else None
    return CommitResponse(ok=True, commit=sha, message="Committed")


@git_router.post("/push", response_model=PushResponse)
async def git_push(req: PushRequest) -> PushResponse:
    _ensure_repo()
    cp = _git("push", req.remote, req.branch)
    if cp.returncode != 0:
        msg = (cp.stderr.decode() or cp.stdout.decode()).strip()
        raise HTTPException(status_code=400, detail=msg)
    return
