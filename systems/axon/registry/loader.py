# systems/axon/registry/loader.py
from __future__ import annotations

import hashlib
import os
import threading
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel


class SourceCfg(BaseModel):
    id: str
    kind: str  # rss | jsonfeed | json | csv | ics | mqtt | webhook
    enabled: bool = True
    url: str | None = None
    topic: str | None = None
    tags: list[str] = []
    schedule: str | None = None
    timeout_sec: int | None = None
    mapping: dict[str, Any] | None = None
    csv: dict[str, Any] | None = None
    auth: dict[str, Any] | None = None  # headers, token, etc.


class Registry(BaseModel):
    version: int
    defaults: dict[str, Any] = {}
    sources: list[SourceCfg] = []


class RegistryManager:
    """
    Hot-reloadable YAML merger for feed sources.
    Later you can swap this to DB-backed without changing adapters.
    """

    def __init__(self, *paths: str):
        self.paths = [p for p in paths if p]
        self._lock = threading.RLock()
        self._fingerprint = ""
        self._merged: Registry = Registry(version=1, defaults={}, sources=[])

    def _load_all(self) -> Registry:
        merged = {"version": 1, "defaults": {}, "sources": []}
        for p in self.paths:
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                doc = yaml.safe_load(f) | {}
                merged["defaults"].update(doc.get("defaults", {}))
                idx = {s["id"]: s for s in merged["sources"]}
                for src in doc.get("sources", []) or []:
                    idx[src["id"]] = {**idx.get(src["id"], {}), **src}
                merged["sources"] = list(idx.values())
        return Registry(**merged)

    def refresh_if_changed(self) -> bool:
        # Use mtimes for quick-change detection
        blob = ""
        for p in self.paths:
            if os.path.exists(p):
                blob += f"{p}:{os.path.getmtime(p)};"
        fp = hashlib.sha1(blob.encode()).hexdigest()
        with self._lock:
            if fp == self._fingerprint:
                return False
            self._merged = self._load_all()
            self._fingerprint = fp
            return True

    def get(self) -> Registry:
        with self._lock:
            return self._merged

    # Convenience
    def iter_enabled(self, kind: str | None = None) -> list[SourceCfg]:
        reg = self.get()
        out: list[SourceCfg] = []
        for s in reg.sources:
            if not s.enabled:
                continue
            if kind and s.kind != kind:
                continue
            out.append(s)
        return out
