from __future__ import annotations

import json
import mimetypes
import os
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from systems.simula.config import settings

# Try to use your existing artifacts package if it exposes compatible funcs
_BACKEND = os.getenv("SIMULA_ARTIFACTS_BACKEND", "auto")  # "auto" | "package" | "fs"

_pkg = None
if _BACKEND in ("auto", "package"):
    try:
        # adjust import to your real package/module path
        import artifacts as _pkg  # e.g. `from artifacts import api as _pkg`
    except Exception:
        _pkg = None

ARTIFACT_DIRS = [
    "artifacts",
    "artifacts/reports",
    "artifacts/proposals",
    ".simula",
    "spec_eval",
]
TEXT_EXTS = {
    ".json",
    ".md",
    ".txt",
    ".log",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".cfg",
    ".ini",
    ".csv",
    ".tsv",
    ".diff",
    ".patch",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".sh",
}
MAX_INLINE_BYTES = 256 * 1024


@dataclass
class Artifact:
    path: str
    size: int
    mtime: float
    type: str
    rel_root: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mtime_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.mtime))
        return d


def _root() -> Path:
    return Path(settings.artifacts_root or (settings.repo_root or ".")).resolve()


# -------- package-backed paths (preferred if available) --------
def _pkg_list(kind: str | None, limit: int) -> dict[str, Any]:
    # Expect your package to offer something like: list(kind=None, limit=200) -> items
    items = _pkg.list(kind=kind, limit=limit)  # type: ignore[attr-defined]
    return {"count": len(items), "items": items, "root": _pkg.root()}  # adjust if needed


def _pkg_read(rel_path: str) -> dict[str, Any]:
    return _pkg.read(rel_path)  # type: ignore[attr-defined]


def _pkg_delete(paths: list[str]) -> dict[str, Any]:
    return _pkg.delete(paths)  # type: ignore[attr-defined]


# -------- filesystem fallback (safe if no package or forced) --------
def _is_textlike(p: Path) -> bool:
    if p.suffix.lower() in TEXT_EXTS:
        return True
    mt, _ = mimetypes.guess_type(str(p))
    return (mt or "").startswith("text/")


def _iter_candidate_files(base: Path) -> Iterable[Path]:
    for d in ARTIFACT_DIRS:
        dp = (base / d).resolve()
        if dp.is_file():
            yield dp
        elif dp.is_dir():
            for fp in dp.rglob("*"):
                if fp.is_file():
                    try:
                        fp.resolve().relative_to(base)  # containment
                    except Exception:
                        continue
                    yield fp


def _infer_type(rel: str, suffix: str) -> str:
    if "reports/" in rel or suffix == ".md":
        return "report"
    if "proposals/" in rel:
        return "proposal"
    if "spec_eval/" in rel and suffix == ".json":
        return "score"
    if rel.endswith("gates.json"):
        return "gates"
    if suffix in (".json", ".yaml", ".yml") and ".simula" in rel:
        return "cache"
    if suffix == ".log":
        return "log"
    return "other"


def _fs_list(kind: str | None, limit: int) -> dict[str, Any]:
    base = _root()
    rows: list[Artifact] = []
    for fp in _iter_candidate_files(base):
        rel = str(fp.relative_to(base))
        t = _infer_type(rel, fp.suffix.lower())
        if kind and t != kind:
            continue
        st = fp.stat()
        rows.append(
            Artifact(path=rel, size=st.st_size, mtime=st.st_mtime, type=t, rel_root=str(base)),
        )
    rows.sort(key=lambda a: (a.mtime, a.size), reverse=True)
    out = [a.to_dict() for a in rows[: max(1, min(1000, limit))]]
    return {"count": len(out), "items": out, "root": str(base)}


def _fs_read(rel_path: str) -> dict[str, Any]:
    base = _root()
    fp = (base / rel_path).resolve()
    fp.relative_to(base)  # containment
    if not fp.exists() or not fp.is_file():
        return {"status": "error", "reason": "not_found"}
    st = fp.stat()
    info = {
        "path": str(fp.relative_to(base)),
        "size": st.st_size,
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
        "textlike": _is_textlike(fp),
    }
    if st.st_size <= MAX_INLINE_BYTES and _is_textlike(fp):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
            try:
                return {
                    "status": "success",
                    "info": info,
                    "content": text,
                    "json": json.loads(text),
                }
            except Exception:
                return {"status": "success", "info": info, "content": text}
        except Exception as e:
            return {"status": "error", "reason": f"read_failed: {e!r}", "info": info}
    return {"status": "success", "info": info}


def _fs_delete(paths: list[str]) -> dict[str, Any]:
    base = _root()
    deleted, failed = [], []
    for rp in paths:
        try:
            fp = (base / rp).resolve()
            fp.relative_to(base)
            if fp.exists() and fp.is_file():
                fp.unlink()
                deleted.append(rp)
            else:
                failed.append({"path": rp, "reason": "not_found"})
        except Exception as e:
            failed.append({"path": rp, "reason": str(e)})
    return {"deleted": deleted, "failed": failed}


# -------- public API (delegates) --------
def list_artifacts(kind: str | None = None, limit: int = 200) -> dict[str, Any]:
    if _pkg and _BACKEND in ("auto", "package"):
        try:
            return _pkg_list(kind, limit)
        except Exception:
            pass
    return _fs_list(kind, limit)


def read_artifact(rel_path: str) -> dict[str, Any]:
    if _pkg and _BACKEND in ("auto", "package"):
        try:
            return _pkg_read(rel_path)
        except Exception:
            pass
    return _fs_read(rel_path)


def delete_artifacts(rel_paths: list[str]) -> dict[str, Any]:
    if _pkg and _BACKEND in ("auto", "package"):
        try:
            return _pkg_delete(rel_paths)
        except Exception:
            pass
    return _fs_delete(rel_paths)
