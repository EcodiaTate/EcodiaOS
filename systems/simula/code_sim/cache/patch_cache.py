# systems/simula/code_sim/cache/patch_cache.py
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def _repo_root() -> Path:
    try:
        from systems.simula.config import settings  # type: ignore

        root = getattr(settings, "repo_root", None)
        if root:
            return Path(root).resolve()
    except Exception:
        pass
    for env in ("SIMULA_WORKSPACE_ROOT", "SIMULA_REPO_ROOT", "PROJECT_ROOT"):
        p = os.getenv(env)
        if p:
            return Path(p).resolve()
    return Path(".").resolve()


def _cache_path() -> Path:
    root = _repo_root()
    p = root / ".simula" / "cache" / "hygiene.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> dict[str, Any]:
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    p = _cache_path()
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _key(diff_text: str) -> str:
    h = hashlib.sha256()
    h.update(diff_text.encode("utf-8", errors="ignore"))
    return h.hexdigest()


@dataclass
class CacheEntry:
    static_ok: bool
    tests_ok: bool
    delta_cov_pct: float
    payload: dict[str, Any]


def get(diff_text: str) -> CacheEntry | None:
    k = _key(diff_text or "")
    with _lock:
        store = _load()
        rec = store.get(k)
        if not rec:
            return None
        try:
            return CacheEntry(
                static_ok=bool(rec.get("static_ok")),
                tests_ok=bool(rec.get("tests_ok")),
                delta_cov_pct=float(rec.get("delta_cov_pct", 0.0)),
                payload=dict(rec.get("payload") or {}),  # repo_rev lives here if present
            )
        except Exception:
            return None


def put(
    diff_text: str,
    *,
    static_ok: bool,
    tests_ok: bool,
    delta_cov_pct: float,
    payload: dict[str, Any],
) -> None:
    k = _key(diff_text or "")
    entry = {
        "static_ok": bool(static_ok),
        "tests_ok": bool(tests_ok),
        "delta_cov_pct": float(delta_cov_pct),
        "payload": payload or {},
    }
    with _lock:
        store = _load()
        store[k] = entry
        _save(store)
