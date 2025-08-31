import asyncio
import os
from collections.abc import Sequence
from typing import Any


async def run_cmd(
    cmd: Sequence[str],
    cwd: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    # Ensure user-site bin dirs (pip --user) are on PATH even under asyncio subprocesses
    env = dict(os.environ)
    extra_bins = ["/home/ecodia/.local/bin", "/root/.local/bin"]
    path = env.get("PATH", "")
    for p in extra_bins:
        if p and p not in path:
            path = path + (":" if path else "") + p
    env["PATH"] = path

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        try:
            proc.kill()
        finally:
            return {"returncode": 124, "stdout": "TIMEOUT"}
    return {"returncode": proc.returncode, "stdout": (out or b"").decode("utf-8", "replace")}
