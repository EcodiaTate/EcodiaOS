# core/utils/paths.py
from __future__ import annotations

import os
from pathlib import Path

# Prefer explicit env first (compose can set this)
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/app")).resolve()

# Fallback auto-detect if the above is wrong (works for local dev too)
SENTINELS = ("app.py", "pyproject.toml", ".git")
cur = Path(__file__).resolve()
for p in (cur, *cur.parents):
    if any((p / s).exists() for s in SENTINELS):
        PROJECT_ROOT = p
        break


def rel(*parts: str | os.PathLike) -> Path:
    """Join onto project root."""
    return PROJECT_ROOT.joinpath(*parts)


# Example convenience dirs
STORAGE_DIR = rel("storage")
MODELS_DIR = rel("models")
LOGS_DIR = rel("logs")
