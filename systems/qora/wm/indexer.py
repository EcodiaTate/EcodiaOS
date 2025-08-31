# systems/qora/wm/indexer.py
from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from systems.qora.wm.service import WMService


def _iter_py(root: str | os.PathLike[str]) -> Iterable[str]:
    root_p = Path(root)
    for p in root_p.rglob("*.py"):
        # skip venvs and build dirs
        s = str(p)
        if any(seg in s for seg in ("/.venv/", "/venv/", "/site-packages/", "/build/", "/dist/")):
            continue
        yield s


def bootstrap_index(root: str = ".") -> int:
    """
    Best-effort workspace bootstrap: index python files for dossier/subgraph hints.
    Non-fatal; returns count of indexed files.
    """
    n = 0
    for fp in _iter_py(root):
        try:
            if WMService.index_file(fp):
                n += 1
        except Exception:
            pass
    return n
