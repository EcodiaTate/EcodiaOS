# systems/simula/code_sim/sandbox/snapshots.py
from __future__ import annotations

import time
from dataclasses import dataclass

from .sandbox import DockerSandbox
from .seeds import seed_config


@dataclass
class Snapshot:
    tag: str
    created_ts: float


async def create_snapshot(tag_prefix: str = "simula") -> Snapshot:
    """
    Create a lightweight workspace snapshot (git commit-ish) inside the sandbox.
    Caller can store the `tag` and later call `restore_snapshot(tag)`.
    """
    ts = time.time()
    tag = f"{tag_prefix}-{int(ts)}"
    async with DockerSandbox(seed_config()).session() as sess:
        await sess._run_tool(["bash", "-lc", "git add -A || true"])
        await sess._run_tool(["bash", "-lc", f"git commit -m {tag!r} || true"])
        await sess._run_tool(["bash", "-lc", f"git tag -f {tag} || true"])
    return Snapshot(tag=tag, created_ts=ts)


async def restore_snapshot(tag: str) -> tuple[bool, str]:
    """
    Restore a previous snapshot tag; returns (ok, message).
    """
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(
            ["bash", "-lc", f"git reset --hard {tag} && git clean -fd || true"],
        )
        ok = out.get("returncode", 0) == 0
        return ok, (out.get("stdout") or out.get("stderr") or "").strip()
