from __future__ import annotations

import hashlib
import io
import re
import tarfile
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

workspace_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    REPO = Path(getattr(settings, "repo_root", ".")).resolve()
    ART = Path(getattr(settings, "artifacts_root", REPO / ".simula")).resolve()
except Exception:  # pragma: no cover
    REPO = Path(".").resolve()
    ART = (REPO / ".simula").resolve()

_DIFF_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.M)


def _paths_from_diff(diff: str) -> list[Path]:
    if not diff:
        return []
    return [REPO / p for p in sorted(set(_DIFF_PATH_RE.findall(diff)))]


class SnapReq(BaseModel):
    # Either list paths explicitly or pass a unified diff.
    paths: list[str] = Field(default_factory=list, description="Repo-relative paths/dirs")
    diff: str = Field(default="", description="Unified diff to infer changed paths")
    include_tests: bool = True
    label: str = Field(default="snapshot")


class SnapResp(BaseModel):
    ok: bool
    file: str
    sha256: str
    bytes: int


@workspace_router.post("/snapshot", response_model=SnapResp)
async def snapshot(req: SnapReq) -> SnapResp:
    paths: list[Path] = [REPO / p for p in req.paths] if req.paths else _paths_from_diff(req.diff)
    if req.include_tests:
        tdir = REPO / "tests"
        if tdir.exists():
            paths.append(tdir)
    if not paths:
        raise HTTPException(status_code=400, detail="no input paths or diff provided")

    paths = [p for p in paths if str(p).startswith(str(REPO)) and p.exists()]
    ART.mkdir(parents=True, exist_ok=True)
    out_dir = ART / "snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    fname = f"{req.label}-{stamp}.tar.gz"
    fpath = out_dir / fname

    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as tar:
        for p in paths:
            if p.is_dir():
                for sub in p.rglob("*"):
                    if sub.is_file():
                        tar.add(sub, arcname=str(sub.relative_to(REPO)))
            else:
                tar.add(p, arcname=str(p.relative_to(REPO)))
    data = bio.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    fpath.write_bytes(data)
    return SnapResp(ok=True, file=str(fpath), sha256=sha, bytes=len(data))
