from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

xref_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    ROOT = str(getattr(settings, "repo_root", os.getcwd()))
except Exception:  # pragma: no cover
    ROOT = os.getcwd()


class FindUsagesRequest(BaseModel):
    symbol: str = Field(
        ...,
        description="Fully-qualified (best-effort) or plain name, e.g., module.Class.method",
    )
    exts: list[str] = Field(default_factory=lambda: [".py"], description="File extensions to scan")


class UsageHit(BaseModel):
    path: str
    line: int
    context: str


class FindUsagesResponse(BaseModel):
    hits: list[UsageHit] = Field(default_factory=list)


def _iter_files(root: str, exts: list[str]) -> list[Path]:
    out: list[Path] = []
    for p, _, files in os.walk(root):
        if ".git" in p or ".venv" in p or "node_modules" in p:
            continue
        for f in files:
            if any(f.endswith(e) for e in exts):
                out.append(Path(p) / f)
    return out


def _identifier_pat(name: str) -> re.Pattern:
    # match name with word boundaries, allowing dot access
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")


@xref_router.post("/find_usages", response_model=FindUsagesResponse)
async def find_usages(req: FindUsagesRequest) -> FindUsagesResponse:
    pat = _identifier_pat(req.symbol.split("::")[-1].split(".")[-1])
    hits: list[UsageHit] = []
    for fp in _iter_files(ROOT, req.exts):
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, ln in enumerate(text.splitlines(), 1):
            if pat.search(ln):
                ctx = ln.strip()
                hits.append(UsageHit(path=str(fp), line=i, context=ctx[:400]))
    hits.sort(key=lambda h: (h.path, h.line))
    return FindUsagesResponse(hits=hits[:5000])
