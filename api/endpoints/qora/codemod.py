from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

codemod_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    ROOT = str(getattr(settings, "repo_root", os.getcwd()))
except Exception:  # pragma: no cover
    ROOT = os.getcwd()

# libcst optional (better rename). Fallback to regex if missing.
try:
    import libcst as cst  # type: ignore
except Exception:  # pragma: no cover
    cst = None


class RenameRequest(BaseModel):
    path: str = Field(..., description="Repo-relative file path")
    old: str = Field(..., min_length=1)
    new: str = Field(..., min_length=1)
    dry_run: bool = True


class ReplaceImportRequest(BaseModel):
    module_from: str
    module_to: str
    glob: bool = True
    dry_run: bool = True


class CodemodResponse(BaseModel):
    ok: bool
    diff: str
    changed_files: list[str] = Field(default_factory=list)


def _unified_diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(True),
            after.splitlines(True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        ),
    )


def _regex_rename(src: str, old: str, new: str) -> str:
    # conservative identifier rename
    pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])")
    return pat.sub(new, src)


@codemod_router.post("/rename_symbol", response_model=CodemodResponse)
async def codemod_rename(req: RenameRequest) -> CodemodResponse:
    path = os.path.normpath(os.path.join(ROOT, req.path))
    if not (os.path.isfile(path) and path.startswith(ROOT)):
        raise HTTPException(status_code=404, detail="file not found")
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    after = text
    if cst:
        try:

            class Renamer(cst.CSTTransformer):
                def __init__(self, old: str, new: str):
                    self.old, self.new = old, new

                def leave_Name(self, original, updated):
                    if original.value == self.old:
                        return updated.with_changes(value=self.new)
                    return updated

            mod = cst.parse_module(text)
            after = mod.visit(Renamer(req.old, req.new)).code
        except Exception:
            after = _regex_rename(text, req.old, req.new)
    else:
        after = _regex_rename(text, req.old, req.new)

    diff = _unified_diff(req.path, text, after)
    if not req.dry_run and diff:
        Path(path).write_text(after, encoding="utf-8")
    return CodemodResponse(ok=True, diff=diff, changed_files=[req.path] if diff else [])


@codemod_router.post("/replace_import", response_model=CodemodResponse)
async def codemod_replace_import(req: ReplaceImportRequest) -> CodemodResponse:
    changed: list[str] = []
    diffs: list[str] = []
    pat_from = re.compile(rf"(^\s*from\s+){re.escape(req.module_from)}(\s+import\s+)", re.M)
    pat_imp = re.compile(rf"(^\s*import\s+){re.escape(req.module_from)}(\s*$|\s+as\s+\w+)", re.M)
    for root, _, files in os.walk(ROOT):
        if ".git" in root or ".venv" in root or "node_modules" in root:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, ROOT)
            text = Path(p).read_text(encoding="utf-8", errors="ignore")
            after = pat_from.sub(rf"\1{req.module_to}\2", text)
            after = pat_imp.sub(rf"\1{req.module_to}\2", after)
            if after != text:
                diffs.append(_unified_diff(rel, text, after))
                changed.append(rel)
                if not req.dry_run:
                    Path(p).write_text(after, encoding="utf-8")
    return CodemodResponse(ok=True, diff="".join(diffs), changed_files=changed)
