# systems/simula/code_sim/repair/ddmin.py
from __future__ import annotations

import re
from dataclasses import dataclass

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config

_HUNK_RE = re.compile(r"^diff --git a/.+?$\n(?:.+\n)+?(?=^diff --git a/|\Z)", re.M)


def _split_hunks(diff_text: str) -> list[str]:
    hunks = _HUNK_RE.findall(diff_text or "")
    return hunks if hunks else ([diff_text] if diff_text else [])


@dataclass
class DDMinResult:
    status: str
    failing_hunk_index: int | None = None
    healed_diff: str | None = None
    notes: str | None = None


async def isolate_and_attempt_heal(
    diff_text: str,
    *,
    pytest_k: str | None = None,
    timeout_sec: int = 900,
) -> DDMinResult:
    """
    Heuristic ddmin: identify a single failing hunk by re-running tests after reverting each hunk.
    If reverting one hunk returns tests to green, emit a healed diff (original minus that hunk).
    """
    chunks = _split_hunks(diff_text)
    if not chunks:
        return DDMinResult(status="error", notes="empty diff")

    # First, confirm that the full patch is actually red
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        ok_apply = await sess.apply_unified_diff(diff_text)
        if not ok_apply:
            return DDMinResult(status="error", notes="cannot apply original diff")
        ok, _ = await sess.run_pytest_select(["tests"], pytest_k or "", timeout=timeout_sec)
        if ok:
            return DDMinResult(status="green", notes="full patch already green; no ddmin needed")

    # Try reverting each hunk and re-testing
    for idx, hunk in enumerate(chunks):
        async with DockerSandbox(cfg).session() as sess:
            # Apply full patch, then revert this single hunk
            if not await sess.apply_unified_diff(diff_text):
                return DDMinResult(status="error", notes="cannot re-apply diff during ddmin")
            _ = await sess.rollback_unified_diff(hunk)  # revert only this hunk
            ok, _ = await sess.run_pytest_select(["tests"], pytest_k or "", timeout=timeout_sec)
            if ok:
                # Capture healed diff from workspace (original minus reverted hunk)
                out = await sess._run_tool(
                    ["bash", "-lc", "git diff --unified=2 --no-color || true"],
                )
                healed = (out or {}).get("stdout") or ""
                return DDMinResult(
                    status="healed",
                    failing_hunk_index=idx,
                    healed_diff=healed,
                    notes="reverted one failing hunk",
                )
    return DDMinResult(status="unhealed", notes="no single-hunk revert could heal")
