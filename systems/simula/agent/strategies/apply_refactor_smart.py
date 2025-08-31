# systems/simula/agent/strategies/apply_refactor_smart.py
from __future__ import annotations

import re

from systems.simula.agent import tools as _t

_HUNK_RE = re.compile(r"^diff --git a/.+?$\n(?:.+\n)+?(?=^diff --git a/|\Z)", re.M)


def _split_unified_diff(diff: str) -> list[str]:
    hunks = _HUNK_RE.findall(diff or "")
    return hunks if hunks else ([diff] if diff else [])


async def apply_refactor_smart(
    diff: str,
    *,
    verify_paths: list[str] | None = None,
) -> dict[str, object]:
    """
    Apply a large diff in smaller hunks, running tests after each chunk.
    If a chunk fails, stop and report the failing hunk index.
    """
    chunks = _split_unified_diff(diff)
    if not chunks:
        return {"status": "error", "reason": "empty diff"}
    verify = verify_paths or ["tests"]
    applied_count = 0
    for i, chunk in enumerate(chunks):
        res = await _t.apply_refactor({"diff": chunk, "verify_paths": verify})
        if res.get("status") != "success":
            return {
                "status": "partial",
                "applied_chunks": applied_count,
                "failed_chunk": i,
                "logs": res.get("logs"),
            }
        applied_count += 1
    return {"status": "success", "applied_chunks": applied_count}
