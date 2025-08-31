from __future__ import annotations

import asyncio
import subprocess


def _git_sync(args: list[str], repo_path: str) -> dict:
    p = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=600,
    )
    return {"rc": p.returncode, "out": p.stdout}


async def _git(args: list[str], repo_path: str) -> dict:
    return await asyncio.to_thread(_git_sync, args, repo_path)


async def ensure_branch(branch: str, repo_path: str):
    """
    If branch exists -> checkout. Else create from current HEAD.
    """
    # does it exist?
    exists = await _git(["rev-parse", "--verify", branch], repo_path)
    if exists["rc"] == 0:
        await _git(["checkout", branch], repo_path)
    else:
        await _git(["checkout", "-b", branch], repo_path)


async def commit_all(repo_path: str, message: str):
    """
    Stage everything and commit if there are changes.
    """
    await _git(["add", "-A"], repo_path)
    status = await _git(["status", "--porcelain"], repo_path)
    if status["rc"] == 0 and status["out"].strip():
        await _git(["commit", "-m", message], repo_path)
