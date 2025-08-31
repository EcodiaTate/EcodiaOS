from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import sys
import time
from types import ModuleType

PLAYBOOK_PKG = "systems.nova.playbooks"


class PlaybookHotReloader:
    """Throttled, safe-ish hot-reloader for playbook modules."""

    def __init__(self, min_interval_sec: float = 2.0) -> None:
        self._mtimes: dict[str, float] = {}
        self._last_check = 0.0
        self._interval = min_interval_sec

    def _iter_modules(self) -> list[ModuleType]:
        mods: list[ModuleType] = []
        pkg = sys.modules.get(PLAYBOOK_PKG)
        if pkg is None:
            pkg = importlib.import_module(PLAYBOOK_PKG)
        pkg_path = pkg.__path__  # type: ignore[attr-defined]
        for m in pkgutil.walk_packages(pkg_path, prefix=PLAYBOOK_PKG + "."):
            try:
                mods.append(importlib.import_module(m.name))
            except Exception:
                # Broken module shouldn’t break market loop
                pass
        return mods

    def check_reload(self) -> None:
        now = time.time()
        if now - self._last_check < self._interval:
            return
        self._last_check = now

        for mod in self._iter_modules():
            try:
                file = inspect.getsourcefile(mod)
                if not file or not os.path.isfile(file):
                    continue
                mtime = os.path.getmtime(file)
                prev = self._mtimes.get(file, 0.0)
                if mtime > prev:
                    importlib.reload(mod)
                    self._mtimes[file] = mtime
            except Exception:
                # Soft failure
                pass
