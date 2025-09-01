# api/endpoints/qora/wm_admin.py
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.utils.net_api import ENDPOINTS, post
from systems.qora.core.code_graph.ingestor import patrol_and_ingest
from systems.synk.core.tools.ingest_state import (
    read_last_commit,
    write_last_commit,
    check_and_mark_processed,
)

logger = logging.getLogger(__name__)
wm_admin_router = APIRouter(tags=["qora"])

IMMUNE_HEADER = "x-ecodia-immune"
DECISION_HEADER = "x-decision-id"
STATE_ID = os.getenv("QORA_INGEST_STATE_ID", "wm")  # state bucket for reindex


# ------------------------------ models ------------------------------
class ReindexReq(BaseModel):
    root: str = Field(default=".", description="Repo root to index")
    force: bool = Field(default=False, description="Force a full rebuild")
    dry_run: bool = Field(default=False, description="Plan only; do not write")
    base_rev: Optional[str] = Field(
        default=None, description="Optional git base revision for incremental indexing"
    )
    bypass_dedupe: bool = Field(
        default=False, description="Ignore commit-key dedupe once (debug escape hatch)"
    )


# ------------------------------ git helpers ------------------------------
def _git(args: list[str], cwd: str | Path) -> tuple[int, str, str]:
    """Run git with args (no leading 'git'). Returns (rc, stdout, stderr)."""
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _ensure_git_env(root: Path) -> None:
    os.environ.setdefault("GIT_DISCOVERY_ACROSS_FILESYSTEM", "1")
    os.environ.setdefault("GIT_WORK_TREE", str(root))
    git_dir = root / ".git"
    if git_dir.exists():
        os.environ.setdefault("GIT_DIR", str(git_dir))


def _git_dirty_summary(root: Path) -> dict[str, Any]:
    """
    Summarize uncommitted changes (tracked + untracked) for *.py only.
    Returns {dirty: bool, files: [str], hash: str}
    Hash includes file path + mtime + size + a small content sample to
    avoid false “already processed” when the set of dirty files is the same.
    """
    def _lines(cmd: list[str]) -> list[str]:
        rc, out, err = _git(cmd, root)
        if rc != 0:
            logger.debug("[WM Admin] git %s failed rc=%s err=%s", " ".join(cmd), rc, err)
            return []
        return out.splitlines() if out else []

    # tracked modified/deleted/renamed vs HEAD (py only)
    tracked = _lines(["diff", "--name-only", "--diff-filter=AMDR", "HEAD", "--", "*.py"])
    # untracked new files (py only)
    untracked = _lines(["ls-files", "--others", "--exclude-standard", "--", "*.py"])
    files = sorted({f for f in (tracked + untracked) if f.strip()})

    h = hashlib.sha256()
    for rel in files:
        p = (root / rel)
        h.update(rel.encode("utf-8"))
        try:
            st = p.stat()
            h.update(str(st.st_mtime_ns).encode("utf-8"))
            h.update(str(st.st_size).encode("utf-8"))
            # small content sample (first 4 KB) to capture edits robustly
            with open(p, "rb") as fp:
                h.update(fp.read(4096))
        except Exception:
            # file might be deleted or transient; still include a marker
            h.update(b"NA")

    return {"dirty": bool(files), "files": files, "hash": h.hexdigest() if files else "0"*64}


def _git_context(root: Path, base_rev_hint: Optional[str]) -> dict[str, Any]:
    _ensure_git_env(root)
    rc, out, err = _git(["rev-parse", "--is-inside-work-tree"], root)
    if rc != 0 or out.lower() != "true":
        return {"is_repo": False, "head": None, "base": None, "reason": "not a git repo"}

    rc_h, head, _ = _git(["rev-parse", "--verify", "--short", "HEAD"], root)
    if rc_h != 0 or not head:
        return {"is_repo": True, "head": None, "base": None, "reason": "no HEAD"}

    if base_rev_hint:
        rc_b, base_chk, _ = _git(["rev-parse", "--verify", "--short", base_rev_hint], root)
        if rc_b == 0 and base_chk:
            return {"is_repo": True, "head": head, "base": base_chk, "reason": None}
        else:
            logger.warning("[WM Admin] base_rev hint '%s' is not valid; will use ingest-state or HEAD", base_rev_hint)

    return {"is_repo": True, "head": head, "base": head, "reason": None}


# ------------------------------ orchestration ------------------------------
_singleflight_lock: asyncio.Lock | None = None

async def _run_reindex(req: ReindexReq) -> dict[str, Any]:
    repo_root = Path(req.root).resolve()
    ctx = _git_context(repo_root, req.base_rev)

    dirty = {"dirty": False, "files": [], "hash": "0" * 64}
    head = ctx.get("head")
    if ctx["is_repo"] and head:
        dirty = _git_dirty_summary(repo_root)

    prev_commit = await read_last_commit(STATE_ID)

    # Decide mode
    if req.force:
        changed_only, why = False, "force=True"
    elif ctx["is_repo"] and head:
        base = req.base_rev or prev_commit or ctx["base"]
        changed_only, why = True, f"incremental from base={base}"
    else:
        changed_only, why = False, f"full-scan (reason: {ctx.get('reason') or 'unknown'})"

    # Build commit-key (dedupe)
    commit_key = None
    if head:
        commit_key = head if not dirty["dirty"] else f"{head}+dirty:{dirty['hash']}"

    # Fast NOOP if clean and already at head
    if (not req.force) and head and (not dirty["dirty"]) and prev_commit and head == prev_commit:
        logger.info("[WM Admin] reindex NOOP: already at HEAD=%s (clean tree)", head)
        return {
            "ok": True, "mode": "noop", "base": prev_commit, "head": head,
            "dirty": False, "reason": "already at head", "result": None
        }

    # Cross-worker dedupe (skip if bypass requested)
    if (not req.force) and (not req.bypass_dedupe) and commit_key:
        already_done = await check_and_mark_processed(commit_key, STATE_ID)
        if already_done:
            logger.info("[WM Admin] reindex NOOP: key %s already processed by another worker", commit_key)
            return {
                "ok": True, "mode": "noop", "base": prev_commit, "head": head,
                "dirty": dirty["dirty"], "reason": "commit key already processed", "result": None
            }

    logger.info(
        "[WM Admin] reindex start: root=%s, dry_run=%s, decided=%s, prev=%s, head=%s, dirty=%s (%d files) key=%s",
        repo_root, req.dry_run, why, prev_commit, head, dirty["dirty"], len(dirty["files"]), commit_key
    )

    result = await patrol_and_ingest(
        root_dir=str(repo_root),
        force=(not changed_only),
        dry_run=req.dry_run,
        changed_only=changed_only,
        state_id=STATE_ID,
    )

    # Persist last_commit only for CLEAN heads (don’t stamp on dirty pseudo-runs)
    if head and not req.dry_run and not dirty["dirty"]:
        upd = await write_last_commit(head, STATE_ID)
        logger.info(
            "[WM Admin] reindex done: ok (commit %s, updated=%s from=%s to=%s)",
            head, upd.get("updated"), upd.get("previous"), upd.get("current")
        )
    else:
        logger.info("[WM Admin] reindex done: ok (dry_run=%s, dirty=%s)", req.dry_run, dirty["dirty"])

    return {
        "ok": True,
        "mode": "changed_only" if changed_only else "full",
        "base": prev_commit,
        "head": head,
        "dirty": dirty["dirty"],
        "result": result,
    }


async def _guarded_reindex(req: ReindexReq) -> dict[str, Any]:
    global _singleflight_lock
    if _singleflight_lock is None:
        _singleflight_lock = asyncio.Lock()
    async with _singleflight_lock:
        return await _run_reindex(req)


# ------------------------------ routes ------------------------------
@wm_admin_router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
async def wm_reindex(body: Optional[ReindexReq] = Body(default=None)) -> JSONResponse:
    req = body or ReindexReq()

    async def _bg():
        res = await _guarded_reindex(req)
        if not res.get("ok"):
            logger.error("[WM Admin] Reindex failed in background: %s", res.get("error"))

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_bg())
    except RuntimeError:
        await _bg()

    content = {
        "accepted": True,
        "root": req.root,
        "force": req.force,
        "dry_run": req.dry_run,
        "base_rev": req.base_rev,
        "bypass_dedupe": req.bypass_dedupe,
        "state_id": STATE_ID,
        "message": "Reindex started",
    }
    headers = {IMMUNE_HEADER: "1", DECISION_HEADER: "admin-reindex"}
    return JSONResponse(content=content, headers=headers)


@wm_admin_router.get("/export")
async def wm_export(fmt: str = "dot") -> dict[str, Any]:
    """Export the current Code Graph via an HTTP call to Qora."""
    try:
        response = await post(ENDPOINTS.QORA_WM_GRAPH_EXPORT, json={"fmt": fmt})
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            raise HTTPException(status_code=500, detail=data.get("reason", "export failed"))
        return {"status": "success", "result": data.get("result")}
    except AttributeError:
        raise HTTPException(
            status_code=500,
            detail="Endpoint 'QORA_WM_GRAPH_EXPORT' not found. Is the API overlay initialized?",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export graph: {e}")


# --- tiny debug endpoint to see detected dirty files/hash ---
@wm_admin_router.get("/dirty")
async def wm_dirty(root: str = ".") -> dict[str, Any]:
    repo_root = Path(root).resolve()
    ctx = _git_context(repo_root, None)
    head = ctx.get("head")
    dirty = _git_dirty_summary(repo_root) if head else {"dirty": False, "files": [], "hash": "0" * 64}
    key = head if not dirty["dirty"] else f"{head}+dirty:{dirty['hash']}" if head else None
    return {"head": head, "dirty": dirty, "commit_key": key, "ctx": ctx}
