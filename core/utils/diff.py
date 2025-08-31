# core/utils/diff.py
from __future__ import annotations

import re

_HUNK_FILE_NEW = re.compile(r"^\+\+\+ b/(.+)$", re.M)
_HUNK_FILE_OLD = re.compile(r"^--- a/(.+)$", re.M)
_DIFF_BLOCK = re.compile(r"(?ms)^diff --git a/.+?$\n(?:.+?\n)*?(?=(?:^diff --git a/)|\Z)")
_RENAME = re.compile(r"^rename to (.+)$", re.M)


def changed_paths_from_unified_diff(diff_text: str) -> list[str]:
    """
    Extract 'b/' side file paths from a unified diff (handles renames).
    Returns a de-duplicated, stable-ordered list.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for block in _DIFF_BLOCK.findall(diff_text or ""):
        # Prefer +++ b/<path> if present
        m = _HUNK_FILE_NEW.search(block)
        if m:
            p = m.group(1).strip()
            if p not in seen:
                paths.append(p)
                seen.add(p)
            continue
        # Fallback to rename lines
        r = _RENAME.search(block)
        if r:
            p = r.group(1).strip()
            if p not in seen:
                paths.append(p)
                seen.add(p)
            continue
        # Very last fallback: --- a/<path>
        m2 = _HUNK_FILE_OLD.search(block)
        if m2:
            p = m2.group(1).strip()
            if p not in seen:
                paths.append(p)
                seen.add(p)
    return paths
