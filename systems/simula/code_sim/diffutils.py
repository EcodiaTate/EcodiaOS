# systems/simula/code_sim/diffutils.py
from __future__ import annotations

import re

_HUNK_HEADER = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@")
_PLUS_FILE = re.compile(r"^\+\+\+\s+b/(.+)$")
_MINUS_FILE = re.compile(r"^---\s+a/(.+)$")


def _is_ws_only_change_line(line: str) -> bool:
    # "+    " / "-\t" etc — purely whitespace payload
    return (line.startswith("+") or line.startswith("-")) and (line[1:].strip() == "")


def drop_whitespace_only_hunks(diff_text: str) -> str:
    """
    Best-effort: remove hunks where *every* +/- change line is whitespace-only.
    We keep headers and context intact. If detection is ambiguous, keep the hunk.
    """
    if not diff_text:
        return diff_text

    out: list[str] = []
    buf: list[str] = []
    in_hunk = False
    hunk_has_non_ws_change = False

    def _flush_hunk():
        nonlocal buf, in_hunk, hunk_has_non_ws_change, out
        if not buf:
            return
        if in_hunk:
            if hunk_has_non_ws_change:
                out.extend(buf)  # keep the hunk
            # else: drop the entire hunk
        else:
            out.extend(buf)
        buf = []
        in_hunk = False
        hunk_has_non_ws_change = False

    for ln in diff_text.splitlines():
        if _HUNK_HEADER.match(ln):
            _flush_hunk()
            in_hunk = True
            hunk_has_non_ws_change = False
            buf.append(ln)
            continue

        if in_hunk:
            # Track whether we see any non-whitespace +/- line
            if (ln.startswith("+") or ln.startswith("-")) and not _is_ws_only_change_line(ln):
                hunk_has_non_ws_change = True
            buf.append(ln)
        else:
            buf.append(ln)

    _flush_hunk()
    return "\n".join(out) + ("\n" if diff_text.endswith("\n") else "")
