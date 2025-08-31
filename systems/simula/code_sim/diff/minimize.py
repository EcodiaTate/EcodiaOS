# systems/simula/code_sim/diff/minimize.py  (whitespace hunk minimizer)
from __future__ import annotations

import re
from collections.abc import Iterable

_HUNK = re.compile(r"(?ms)^diff --git a/.+?$\n(?:.+?\n)*?(?=(?:^diff --git a/)|\Z)")


def _is_whitespace_only(block: str) -> bool:
    plus = [l for l in block.splitlines() if l.startswith("+") and not l.startswith("+++")]
    minus = [l for l in block.splitlines() if l.startswith("-") and not l.startswith("---")]

    def _strip_payload(ls: Iterable[str]) -> str:
        return "".join(re.sub(r"\s+", "", l[1:]) for l in ls)

    return _strip_payload(plus) == _strip_payload(minus)


def drop_whitespace_only_hunks(diff_text: str) -> str:
    blocks = _HUNK.findall(diff_text or "")
    keep = [b for b in blocks if not _is_whitespace_only(b)]
    return "".join(keep) if keep else diff_text
