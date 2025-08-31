from __future__ import annotations

import os
from pathlib import Path

# Default to container mount. If you centralize settings, import from deps.
REPO_ROOT = Path(os.environ.get("SIMULA_REPO_ROOT", "/workspace")).resolve()

# Anything outside repo or touching host/daemon sockets is blocked.
BLOCKLIST_ABS = {
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/var/run/docker.sock",
}
BLOCKED_SUFFIXES = {".sock"}


def _is_subpath(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except Exception:
        return False


def safe_patch_paths(paths: list[Path]) -> bool:
    """
    Returns True iff all paths resolve under REPO_ROOT and avoid blocklisted locations.
    """
    for p in paths:
        rp = p.resolve()
        # Must stay inside repo
        if not _is_subpath(rp, REPO_ROOT):
            return False
        # No sockets / weird devices
        if any(str(rp).startswith(b) for b in BLOCKLIST_ABS):
            return False
        if any(str(rp).endswith(suf) for suf in BLOCKED_SUFFIXES):
            return False
    return True
