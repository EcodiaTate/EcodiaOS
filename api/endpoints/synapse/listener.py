from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

router = APIRouter(prefix="/cicd", tags=["cicd"])

REPO_ROOT = Path(os.getenv("REPO_ROOT", Path.cwd())).resolve()
APPROVED_DIR = REPO_ROOT / ".ecodia" / "approved_patches"
APPROVED_DIR.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str], cwd: Path) -> None:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}",
        )


def _apply_patch_to_worktree(diff_text: str, branch_name: str) -> str:
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        shutil.copytree(REPO_ROOT, tmp / "repo", dirs_exist_ok=True)
        repo = tmp / "repo"
        _run(["git", "init"], repo)
        _run(["git", "add", "-A"], repo)
        _run(["git", "commit", "-m", "snapshot"], repo)
        patch_file = tmp / "patch.diff"
        patch_file.write_text(diff_text, encoding="utf-8")
        _run(["git", "apply", str(patch_file)], repo)
        _run(["git", "checkout", "-b", branch_name], repo)
        _run(["git", "add", "-A"], repo)
        _run(["git", "commit", "-m", f"EcodiaOS self-upgrade: {branch_name}"], repo)
        out_patch = APPROVED_DIR / f"{branch_name}.diff"
        out_patch.write_text(diff_text, encoding="utf-8")
    return str(out_patch)


@router.post("/listener/governor/upgrade/approved")
async def on_governor_upgrade_approved(data: dict[str, Any] = Body(...)):
    try:
        proposal = data.get("payload", {}).get("proposal") or data.get("proposal")
        if not proposal or not isinstance(proposal, dict):
            raise ValueError("Missing 'proposal' in payload")
        diff_text = proposal.get("diff") or ""
        proposal.get("summary") or "upgrade"
        if not diff_text.strip():
            raise ValueError("Proposal diff is empty")

        branch = f"eos-upgrade-{abs(hash(diff_text)) % 10_000_000}"
        patch_path = _apply_patch_to_worktree(diff_text, branch)

        return {"status": "accepted", "branch": branch, "patch_file": patch_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
