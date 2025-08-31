from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

rg_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    ROOT = Path(getattr(settings, "repo_root", ".")).resolve()
except Exception:
    ROOT = Path(".").resolve()


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


class SearchReq(BaseModel):
    query: str
    globs: list[str] = Field(default_factory=lambda: ["*.py", "*.md", "*.toml", "*.yaml", "*.yml"])
    max_results: int = 500
    context: int = 2


class Hit(BaseModel):
    path: str
    line: int
    text: str


class SearchResp(BaseModel):
    ok: bool
    hits: list[Hit] = Field(default_factory=list)
    engine: str = "rg"  # or "python"


@rg_router.post("/search", response_model=SearchResp)
async def search_rg(req: SearchReq) -> SearchResp:
    if _have("rg"):
        args = [
            "rg",
            "--json",
            "-n",
            "-C",
            str(req.context),
            req.query,
            "--max-count",
            str(req.max_results),
        ]
        for g in req.globs:
            args += ["-g", g]
        cp = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        hits: list[Hit] = []
        for line in cp.stdout.splitlines():
            try:
                ev = json.loads(line)
                if ev.get("type") == "match":
                    m = ev["data"]["lines"]["text"].rstrip("\n")
                    path = ev["data"]["path"]["text"]
                    line_no = int(ev["data"]["line_number"])
                    hits.append(Hit(path=path, line=line_no, text=m))
                    if len(hits) >= req.max_results:
                        break
            except Exception:
                continue
        return SearchResp(ok=True, hits=hits, engine="rg")
    # Fallback mini-scan
    import re

    pat = re.compile(req.query)
    hits: list[Hit] = []
    for p, _, files in os.walk(ROOT):
        if ".git" in p or ".venv" in p or "node_modules" in p:
            continue
        for f in files:
            if not any(Path(f).match(g) for g in req.globs):
                continue
            full = Path(p, f)
            try:
                txt = full.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for i, ln in enumerate(txt.splitlines(), 1):
                if pat.search(ln):
                    hits.append(Hit(path=str(full.relative_to(ROOT)), line=i, text=ln.strip()))
                    if len(hits) >= req.max_results:
                        return SearchResp(ok=True, hits=hits, engine="python")
    return SearchResp(ok=True, hits=hits, engine="python")
