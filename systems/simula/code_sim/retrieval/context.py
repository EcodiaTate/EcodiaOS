# simula/code_sim/retrieval/context.py
"""
High‑Signal Code Retrieval for Patch Generation

Mission
-------
Feed the LLM diff generator with the *most relevant, compact* slices of the repo:
registry, nearby modules, test oracles, and any obvious spec/schema anchors.

Principles
----------
- **Deterministic & fast**: pure stdlib, linear scans with hard byte caps.
- **Signal‑dense**: prefer definitions, public APIs, and assertions over boilerplate.
- **Safe**: never slurp secrets; ignore large binaries; enforce size & file count limits.
- **Composable**: small helpers you can reuse in mutators/evaluators.

Public API
----------
default_neighbor_globs() -> list[str]
gather_neighbor_snippets(repo_root: Path, file_rel: str) -> dict[path->snippet]
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

# -------- Tunables (conservative defaults) --------

MAX_FILES = 24  # hard cap on files collected
MAX_BYTES_PER_FILE = 4_000  # truncate each file to this many bytes
MAX_TOTAL_BYTES = 48_000  # overall cap
PY_EXTS = {".py"}
TEXT_EXTS = {".md", ".rst", ".txt", ".yaml", ".yml", ".toml", ".ini"}
IGNORE_DIRS = {
    ".git",
    ".simula",
    ".venv",
    "venv",
    ".mypy_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}

# Heuristic weights for ranking neighbors
WEIGHTS = {
    "tests": 1.0,
    "registry": 0.9,
    "same_pkg": 0.8,
    "same_dir": 0.7,
    "docs": 0.4,
    "spec": 0.85,
    "schemas": 0.6,
}

# Conventional anchor paths used elsewhere in EOS; safe if missing
CONVENTIONAL_ANCHORS = [
    "systems/synk/core/tools/registry.py",
    "systems/synk/specs/schema.py",
    "systems/axon/specs/schema.py",
]

# --------------------------------------------------


def default_neighbor_globs() -> list[str]:
    """Return the default set of globs we consider for snippets."""
    return [
        "systems/**/*.py",
        "tests/**/*.py",
        "tests/**/*.md",
        "docs/**/*.*",
        "examples/**/*.py",
        "pyproject.toml",
        "README.md",
    ]


def _is_textual(path: Path) -> bool:
    if path.suffix in PY_EXTS | TEXT_EXTS:
        return True
    # Basic sniff: avoid likely binaries
    try:
        b = path.read_bytes()[:512]
    except Exception:
        return False
    if b"\x00" in b:
        return False
    try:
        b.decode("utf-8")
        return True
    except Exception:
        return False


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    # Keep header and tail (often contains exports/tests) with an ellipsis in the middle
    head = text[: int(limit * 0.7)]
    tail = text[-int(limit * 0.25) :]
    return head + "\n# …\n" + tail


def _read_text(path: Path, limit: int = MAX_BYTES_PER_FILE) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    return _shorten(data, limit)


def _iter_globs(root: Path, patterns: Iterable[str]) -> Iterator[Path]:
    for pat in patterns:
        yield from root.glob(pat)


def _norm_rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root).as_posix())
    except Exception:
        return p.as_posix()


@dataclass(frozen=True)
class Neighbor:
    path: Path
    rel: str
    score: float
    reason: str


def _rank_neighbors(root: Path, primary: Path, candidates: Iterable[Path]) -> list[Neighbor]:
    """
    Assign heuristic scores to candidate files based on proximity and role.
    """
    _norm_rel(root, primary)
    primary_dir = primary.parent
    primary_pkg = _pkg_root(primary)

    scored: list[Neighbor] = []
    for p in candidates:
        if not p.exists() or p.is_dir():
            continue
        # skip ignores
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        if not _is_textual(p):
            continue

        rel = _norm_rel(root, p)

        score = 0.0
        reason = []

        if rel.startswith("tests/") or "/tests/" in rel:
            score += WEIGHTS["tests"]
            reason.append("tests")

        if rel.endswith("registry.py") and "tools" in rel:
            score += WEIGHTS["registry"]
            reason.append("registry")

        if rel.endswith("schema.py") or "/specs/" in rel:
            score += WEIGHTS["spec"]
            reason.append("spec")

        if rel.startswith("docs/") or rel.endswith(".md"):
            score += WEIGHTS["docs"]
            reason.append("docs")

        # local proximity
        if primary_pkg and p.is_relative_to(primary_pkg):
            score += WEIGHTS["same_pkg"]
            reason.append("same_pkg")
        elif p.parent == primary_dir:
            score += WEIGHTS["same_dir"]
            reason.append("same_dir")

        if score == 0.0:
            # slight baseline for any python file near target
            if p.suffix in PY_EXTS:
                score = 0.2
                reason.append("nearby_py")

        scored.append(Neighbor(path=p, rel=rel, score=score, reason=",".join(reason) or "other"))

    scored.sort(key=lambda n: n.score, reverse=True)
    return scored


def _pkg_root(p: Path) -> Path | None:
    """
    Best-effort: walk upwards while __init__.py exists, return the top-most.
    """
    cur = p if p.is_dir() else p.parent
    top = None
    while True:
        init = cur / "__init__.py"
        if init.exists():
            top = cur
            if cur.parent == cur:
                break
            cur = cur.parent
            continue
        break
    return top


def _collect_candidates(root: Path, primary: Path) -> list[Path]:
    pats = default_neighbor_globs()
    cands = list(_iter_globs(root, pats))
    # Include conventional anchors even if not hit by globs
    for rel in CONVENTIONAL_ANCHORS:
        ap = (root / rel).resolve()
        if ap.exists():
            cands.append(ap)
    # Include siblings in the same dir as primary
    if primary.exists():
        for sib in primary.parent.glob("*"):
            if sib.is_file():
                cands.append(sib)
    # Dedup
    seen = set()
    uniq = []
    for p in cands:
        try:
            rp = p.resolve()
        except Exception:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(rp)
    return uniq


_SIG_RE = re.compile(r"^\s*def\s+([a-zA-Z_]\w*)\s*\((.*?)\)\s*->?\s*.*?:", re.MULTILINE)
_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s*(\(|:)", re.MULTILINE)
_ASSERT_RE = re.compile(r"^\s*assert\s+.+$", re.MULTILINE)


def _high_signal_slice(text: str, *, limit: int) -> str:
    """
    Prefer:
      - top‑of‑file imports & constants block
      - function/class signatures (defs/classes)
      - test assertions
    Keep order; trim aggressively.
    """
    if len(text) <= limit:
        return text

    lines = text.splitlines()
    out: list[str] = []

    # 1) top header/import block (first ~80 lines)
    head = lines[: min(80, len(lines))]
    out += head

    # 2) defs/classes signatures (not bodies)
    sigs = []
    for m in _SIG_RE.finditer(text):
        sigs.append(m.group(0))
    for m in _CLASS_RE.finditer(text):
        sigs.append(m.group(0))
    if sigs:
        out.append("\n# --- signatures ---")
        out += sigs[:80]

    # 3) assertions (from tests)
    asserts = _ASSERT_RE.findall(text)
    if asserts:
        out.append("\n# --- assertions ---")
        out += asserts[:80]

    snippet = "\n".join(out)
    return _shorten(snippet, limit)


def gather_neighbor_snippets(repo_root: Path, file_rel: str) -> dict[str, str]:
    """
    Return a mapping of {rel_path: snippet_text} with hard caps respected.
    Ranking favors tests, registries, specs, then local proximity.
    """
    root = repo_root.resolve()
    primary = (root / file_rel).resolve()
    total_budget = MAX_TOTAL_BYTES

    # collect and rank
    cands = _collect_candidates(root, primary)
    ranked = _rank_neighbors(root, primary, cands)

    out: dict[str, str] = {}
    for nb in ranked:
        if len(out) >= MAX_FILES or total_budget <= 0:
            break
        try:
            raw = _read_text(nb.path, limit=MAX_BYTES_PER_FILE * 2)  # read a bit more; slice later
        except Exception:
            continue
        if not raw:
            continue
        # choose a high-signal slice
        snippet = _high_signal_slice(raw, limit=MAX_BYTES_PER_FILE)
        if not snippet.strip():
            continue

        # enforce overall budget
        budgeted = snippet[: min(len(snippet), total_budget)]
        total_budget -= len(budgeted)
        out[nb.rel] = budgeted

    return out
