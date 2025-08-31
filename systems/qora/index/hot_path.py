# systems/qora/index/hot_path.py
from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1024)
def symbol_slice(symbol: str) -> dict[str, object]:
    """
    Very lightweight placeholder: return last-modified time and file size for symbol’s file.
    Real impl would query Qora index. Kept simple for drop-in use.
    """
    p = Path(symbol.split("::")[0])
    return {
        "symbol": symbol,
        "exists": p.exists(),
        "mtime": p.stat().st_mtime if p.exists() else None,
        "size": p.stat().st_size if p.exists() else None,
        "ts": time.time(),
    }
