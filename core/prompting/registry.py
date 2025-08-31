# core/prompting/registry.py
# --- PROJECT SENTINEL UPGRADE (FINAL) ---
from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import ValidationError

from .spec import PromptSpec

try:
    import yaml
except ImportError:
    yaml = None

# Robust pathing ensures the registry always looks in the correct directory.
PROMPTS_ROOT = Path(__file__).parent.parent.resolve()  # Resolves to the 'core' directory
DEFAULT_SPEC_DIR = PROMPTS_ROOT / "prompting/promptspecs"


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
        print(
            f"[PromptSpecRegistry] Initializing and scanning for PromptSpecs in: {self.directory.resolve()}",
        )
        self._by_id: dict[str, _SpecEntry] = {}
        self._by_scope: dict[str, _SpecEntry] = {}
        self._last_scan_time = 0.0
        self._ensure_dir_exists()

    def _ensure_dir_exists(self):
        """Creates the promptspecs directory if it doesn't exist."""
        self.directory.mkdir(parents=True, exist_ok=True)

    def _scan_and_load_files(self) -> None:
        """Scans the directory for spec files and loads/reloads them if they are new or modified."""
        for path in self.directory.glob("**/*.y*ml"):
            self._load_if_needed(path)
        for path in self.directory.glob("**/*.json"):
            self._load_if_needed(path)
        self._last_scan_time = time.time()

    def _load_if_needed(self, path: Path):
        """Loads a single file if it's new or has been modified since the last scan."""
        try:
            mtime = path.stat().st_mtime
            source_path_str = str(path)

            # Find if we have an existing entry for this file path
            existing_entry = next(
                (e for e in self._by_id.values() if e.source == source_path_str),
                None,
            )

            if not existing_entry or existing_entry.mtime < mtime:
                spec = self._parse_spec_file(path)
                if spec:
                    entry = _SpecEntry(spec, source=source_path_str, mtime=mtime)
                    self._by_id[spec.id] = entry
                    self._by_scope[spec.scope] = entry
        except FileNotFoundError:
            # File might be deleted between glob and stat; ignore.
            pass

    def _parse_spec_file(self, path: Path) -> PromptSpec | None:
        """Parses a single YAML or JSON file into a PromptSpec object."""
        try:
            raw_content = path.read_text(encoding="utf-8")
            if path.suffix.lower() in (".yaml", ".yml"):
                if yaml is None:
                    print(
                        f"[PromptSpecRegistry] WARNING: PyYAML not installed but YAML spec found at {path}. Skipping.",
                    )
                    return None
                data = yaml.safe_load(raw_content) or {}
            else:
                data = json.loads(raw_content)

            return PromptSpec(**data)
        except (ValidationError, json.JSONDecodeError, Exception) as e:
            # This is a key resilience feature: log the error but don't crash the service.
            print(f"[PromptSpecRegistry] ERROR: Failed to load or validate spec file {path}: {e}")
            return None

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
        _registry._scan_and_load_files()  # Initial load
    return _registry
