# core/prompting/registry.py
# --- PROJECT SENTINEL UPGRADE (FINAL & FIXED) ---
from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Set

from pydantic import ValidationError

from .spec import PromptSpec

try:
    import yaml  # type: ignore
except Exception:  # PyYAML optional
    yaml = None  # type: ignore

# Robust pathing ensures the registry always looks in the correct directory.
PROMPTS_ROOT = Path(__file__).parent.parent.resolve()  # -> '<repo>/core'
DEFAULT_SPEC_DIR = PROMPTS_ROOT / "prompting" / "promptspecs"


# Debounce rescans to reduce log spam; override with env if needed.
RESCAN_SECONDS = float(os.getenv("PROMPTSPEC_RESCAN_SECONDS", "1.25"))
VERBOSE = os.getenv("PROMPTSPEC_VERBOSE", "1") not in ("0", "false", "False")


class _SpecEntry:
    """Internal cache entry for a loaded PromptSpec."""

    def __init__(self, spec: PromptSpec, source: str, mtime: float):
        self.spec = spec
        self.source = source
        self.mtime = mtime


class PromptSpecRegistry:
    """
    Loads, caches, and hot-reloads PromptSpec documents from YAML/JSON files.
    Maps specs by both 'id' and 'scope' for efficient lookup.
    """

    def __init__(self, directory: Path = DEFAULT_SPEC_DIR):
        self.directory = directory
        print(f"[PromptSpecRegistry] Init at: {self.directory.resolve()}")
        self._by_id: dict[str, _SpecEntry] = {}
        self._by_scope: dict[str, _SpecEntry] = {}
        self._last_scan_time = 0.0

    # -----------------------
    # Filesystem / scanning
    # -----------------------

    def _should_rescan(self) -> bool:
        now = time.time()
        return (now - self._last_scan_time) >= RESCAN_SECONDS

    def _scan_and_load_files(self, force: bool = False) -> None:
        """Scans the directory for spec files and loads/reloads/deletes as needed."""
        if not force and not self._should_rescan():
            return

        all_paths = list(self.directory.glob("**/*.y*ml")) + list(self.directory.glob("**/*.json"))
        current_sources: set[str] = set()
        for path in all_paths:
            spath = str(path)
            current_sources.add(spath)
            self._load_if_needed(path)

        loaded_sources = {entry.source for entry in self._by_id.values()}
        deleted_sources = loaded_sources - current_sources
        for src in deleted_sources:
            self._unregister_by_source(src)

        self._last_scan_time = time.time()

    def _unregister_by_source(self, source_path: str) -> None:
        """Removes all specs that came from a specific file path."""
        ids_to_remove = [
            sid for sid, entry in list(self._by_id.items()) if entry.source == source_path
        ]
        for spec_id in ids_to_remove:
            entry = self._by_id.pop(spec_id, None)
            if entry and entry.spec.scope in self._by_scope:
                if self._by_scope.get(entry.spec.scope, None) is entry:
                    del self._by_scope[entry.spec.scope]

    def _load_if_needed(self, path: Path) -> None:
        """Loads a single file if it's new or has been modified since the last scan."""
        try:
            mtime = path.stat().st_mtime
            source_path_str = str(path)
            existing_entry: _SpecEntry | None = next(
                (e for e in self._by_id.values() if e.source == source_path_str),
                None,
            )
            if not existing_entry or existing_entry.mtime < mtime:
                self._unregister_by_source(source_path_str)
                specs = self._parse_spec_file(path)
                for spec in specs:
                    if not spec:
                        continue
                    entry = _SpecEntry(spec, source=source_path_str, mtime=mtime)
                    prior = self._by_scope.get(spec.scope)
                    if prior and prior.mtime > mtime:
                        continue
                    self._by_id[spec.id] = entry
                    self._by_scope[spec.scope] = entry
        except FileNotFoundError:
            pass

    def _parse_spec_file(self, path: Path) -> list[PromptSpec]:
        """
        Parses a YAML or JSON file. Handles both a single spec object
        and a list of spec objects in the same file.
        """
        try:
            raw_content = path.read_text(encoding="utf-8")
            if not raw_content.strip():
                return []
            if path.suffix.lower() in (".yaml", ".yml"):
                if yaml is None:
                    return []
                data = yaml.safe_load(raw_content) or {}
            else:
                data = json.loads(raw_content)
            if isinstance(data, list):
                return [PromptSpec(**item) for item in data]
            elif isinstance(data, dict):
                return [PromptSpec(**data)]
            else:
                return []
        except (ValidationError, json.JSONDecodeError, Exception) as e:
            # Add a warning for easier debugging
            warnings.warn(f"Failed to parse or validate spec file '{path}': {e}")
            return []

    # -----------------------
    # Public API
    # -----------------------

    def get_by_id(self, spec_id: str) -> PromptSpec | None:
        self._scan_and_load_files()
        entry = self._by_id.get(spec_id)
        return entry.spec if entry else None

    def get_by_scope(self, scope: str) -> PromptSpec | None:
        self._scan_and_load_files()
        entry = self._by_scope.get(scope)
        return entry.spec if entry else None


# --- Singleton Accessor ---
_registry: PromptSpecRegistry | None = None


def get_registry() -> PromptSpecRegistry:
    """Provides a global singleton instance of the PromptSpecRegistry."""
    global _registry
    if _registry is None:
        _registry = PromptSpecRegistry()
        _registry._scan_and_load_files(force=True)  # Initial load
    return _registry
