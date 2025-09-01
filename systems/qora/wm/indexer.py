# systems/qora/wm/indexer.py
from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from systems.qora.wm.service import WMService

# Skips keep noise down during bootstrap scans
_SKIP_SEGMENTS: Final[tuple[str, ...]] = (
    "/.git/",
    "/.venv/",
    "/venv/",
    "/site-packages/",
    "/node_modules/",
    "/build/",
    "/dist/",
    "/__pycache__/",
    "/.mypy_cache/",
)
_EXTS: Final[tuple[str, ...]] = (".py",)  # extend here if you want .pyi, etc.


def _should_skip(path_str: str) -> bool:
    return any(seg in path_str for seg in _SKIP_SEGMENTS)


def _iter_files(root: str | os.PathLike[str], exts: Iterable[str] = _EXTS) -> Iterable[str]:
    root_p = Path(root)
    for p in root_p.rglob("*"):
        if not p.is_file():
            continue
        s = str(p)
        if _should_skip(s):
            continue
        if p.suffix.lower() in exts:
            yield s


def bootstrap_index(root: str = ".") -> int:
    """
    Best-effort workspace bootstrap: index python files for dossier/subgraph hints.
    Non-fatal; returns count of indexed files.
    """
    n = 0
    for fp in _iter_files(root):
        try:
            if WMService.index_file(fp):
                n += 1
        except Exception:
            # Intentionally swallow: bootstrap is advisory
            # (WMService should log details internally)
            pass
    return n
