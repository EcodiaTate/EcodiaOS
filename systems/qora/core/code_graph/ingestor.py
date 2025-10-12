# systems/qora/core/code_graph/ingestor.py
# --- INCREMENTAL INDEXER (FINAL, global lookup + full-pass rel rebuild) ---
from __future__ import annotations

import ast
import hashlib
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Optional ADR front matter support (pip package: python-frontmatter)
try:
    import frontmatter  # import name: frontmatter, package: python-frontmatter
except Exception:
    frontmatter = None  # fallback mode enabled below

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================
VECTOR_DIM = 3072
STD_LIBS = {
    # Core runtime
    "sys",
    "builtins",
    "types",
    "inspect",
    "importlib",
    "importlib_metadata",
    "importlib_resources",
    "site",
    "sysconfig",
    "runpy",
    "pydoc",
    "trace",
    "tracemalloc",
    "faulthandler",
    "gc",
    "warnings",
    # OS / filesystem
    "os",
    "pathlib",
    "stat",
    "shutil",
    "glob",
    "fnmatch",
    "fileinput",
    "tempfile",
    "tarfile",
    "zipfile",
    "zipimport",
    "gzip",
    "bz2",
    "lzma",
    "zlib",
    "mmap",
    # I/O, text, data formats
    "io",
    "codecs",
    "string",
    "textwrap",
    "re",
    "csv",
    "configparser",
    "plistlib",
    "json",
    "sqlite3",
    "dbm",
    # Math & number crunching
    "math",
    "cmath",
    "decimal",
    "fractions",
    "statistics",
    "random",
    "numbers",
    # Cryptography-ish & encoding
    "hashlib",
    "hmac",
    "secrets",
    "base64",
    "binascii",
    # Dates, locales, i18n
    "datetime",
    "calendar",
    "locale",
    "gettext",
    "zoneinfo",
    # Concurrency & async
    "threading",
    "queue",
    "multiprocessing",
    "concurrent",
    "asyncio",
    "subprocess",
    "sched",
    "signal",
    "selectors",
    "select",
    # Networking & protocols
    "socket",
    "ssl",
    "ipaddress",
    "http",
    "urllib",
    "ftplib",
    "poplib",
    "imaplib",
    "smtplib",
    "nntplib",
    "telnetlib",
    "uuid",
    "webbrowser",
    "cgi",
    "cgitb",
    "wsgiref",
    "xmlrpc",
    # Markup, parsing
    "html",
    "html5lib",  # (html5lib is not stdlib; remove if you want *strict* stdlib only)
    "xml",
    "xmltodict",  # (xmltodict is not stdlib; remove for strictness)
    "email",
    # Data persistence & serialization
    "pickle",
    "pickletools",
    "copy",
    "shelve",
    "marshal",
    # Introspection, meta, language utilities
    "abc",
    "enum",
    "typing",
    "dataclasses",
    "contextlib",
    "contextvars",
    "functools",
    "itertools",
    "operator",
    "weakref",
    # CLI utils
    "argparse",
    "getopt",
    "readline",
    "cmd",
    "shlex",
    # Debugging & testing
    "traceback",
    "pprint",
    "doctest",
    "unittest",
    "unittest.mock",
    "timeit",
    "pdb",
    "cProfile",
    "profile",
    # Time & OS details
    "time",
    "platform",
    "resource",  # resource is POSIX-only
    # GUI / audio (platform availability varies)
    "tkinter",
    "curses",
    "tty",
    "termios",
    "audioop",
    "wave",
    "aifc",
    "sunau",
    "chunk",
    "colorsys",
    "imghdr",
    # System integration
    "ctypes",
    "uuid",
    "venv",
    "ensurepip",
    # Packaging/distribution (distutils is deprecated; still present on many)
    "distutils",
}
ADR_GLOB = "docs/adr/**/*.md"

# Embedding strategy metadata (bump EMBEDDING_VERSION to force a global refresh)
EMBEDDING_VERSION = 1
EMBEDDING_MODEL = "gemini-embedding-001"

# Labels
LABEL_CODE = "Code"
LABEL_CODEFILE = "CodeFile"

# Builtins set for quick external resolution
try:
    import builtins as _builtins_mod  # type: ignore

    BUILTINS = set(dir(_builtins_mod))
except Exception:
    BUILTINS = set()

TYPING_WORDS = {
    "typing",
    "Optional",
    "List",
    "Dict",
    "Set",
    "Tuple",
    "Union",
    "Literal",
    "Annotated",
    "Callable",
    "Coroutine",
    "Awaitable",
    "Any",
    "Self",
    "Type",
    "TypeVar",
    "Generic",
    "Iterable",
    "Iterator",
    "Mapping",
    "Sequence",
    "MutableMapping",
    "MutableSequence",
    "Collection",
    "Reversible",
    "Protocol",
    "ParamSpec",
    "Concatenate",
    "NoReturn",
    "Never",
}


# =============================================================================
# Helpers
# =============================================================================
def _fqn(path: Path, node: ast.AST | None = None, relative_to: Path = Path(".")) -> str:
    """
    Build a stable FQN: "<rel_path>::<symbol>" or "<rel_path>" for files.
    rel_path uses forward slashes.
    """
    path_str = str(path.relative_to(relative_to)).replace("\\", "/")
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return f"{path_str}::{node.name}"
    return path_str


def _hash_text(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _hash_bytes(b: bytes) -> str:
    return hashlib.blake2b(b, digest_size=16).hexdigest()


def _path_to_module(path: Path, repo_root: Path) -> str:
    return str(path.relative_to(repo_root)).replace("\\", "/").replace(".py", "").replace("/", ".")


def _node_source_and_doc(node: ast.AST, source: str) -> tuple[str, str]:
    """
    Extract the exact source slice for a class/function plus its docstring.
    We hash (source + doc) to detect meaningful changes.
    """
    lines = source.splitlines()
    start = getattr(node, "lineno", 1) - 1
    end = getattr(node, "end_lineno", start + 1)
    snippet = "\n".join(lines[start:end])
    doc = ast.get_docstring(node) or ""
    return snippet, doc


# =============================================================================
# Git integration (optional; fall back to full scan)
# =============================================================================
async def _get_last_commit_from_graph(state_id: str = "default") -> str | None:
    rows = await cypher_query(
        """
        MATCH (s:IngestState {id:$id})
        RETURN CASE WHEN s.last_commit = '' THEN null ELSE s.last_commit END AS last
        LIMIT 1
        """,
        {"id": state_id},
    )
    return rows[0]["last"] if rows else None


def _git_worktree_changes(repo_root: Path) -> list[tuple[str, Path | None, Path | None]]:
    """
    Returns (status, old_path, new_path) for worktree changes since HEAD, covering:
    - Unstaged tracked (ws)
    - Staged tracked (index, --cached)
    - Untracked new files
    """
    changes: list[tuple[str, Path | None, Path | None]] = []
    seen: set[tuple[str, str, str]] = set()  # (st, old_rel or "", new_rel or "")

    def _lines(cmd: list[str]) -> list[str]:
        try:
            out = subprocess.check_output(cmd, cwd=str(repo_root)).decode()
            return out.splitlines()
        except Exception:
            return []

    ws = _lines(
        [
            "git",
            "diff",
            "--name-status",
            "--find-renames",
            "--diff-filter=AMDR",
            "HEAD",
            "--",
            "*.py",
        ]
    )
    idx = _lines(
        [
            "git",
            "diff",
            "--cached",
            "--name-status",
            "--find-renames",
            "--diff-filter=AMDR",
            "HEAD",
            "--",
            "*.py",
        ]
    )
    new = _lines(["git", "ls-files", "--others", "--exclude-standard", "--", "*.py"])

    def _add(st: str, oldp: Path | None, newp: Path | None):
        key = (
            st,
            str(oldp.relative_to(repo_root)) if oldp else "",
            str(newp.relative_to(repo_root)) if newp else "",
        )
        if key in seen:
            return
        seen.add(key)
        changes.append((st, oldp, newp))

    for line in ws + idx:
        if not line.strip():
            continue
        parts = line.split("\t")
        tag = parts[0]
        if tag.startswith("R"):
            oldp, newp = repo_root / parts[1], repo_root / parts[2]
            _add("R", oldp, newp)
        else:
            st, pth = tag, parts[1]
            if st in ("A", "M"):
                _add(st, None, repo_root / pth)
            elif st == "D":
                _add("D", repo_root / pth, None)

    for p in new:
        if p.strip():
            _add("A", None, repo_root / p)

    return changes


async def _set_last_commit_in_graph(commit: str, state_id: str = "default") -> None:
    await cypher_query(
        "MERGE (s:IngestState {id:$id}) SET s.last_commit = $c, s.updated_at = timestamp()",
        {"id": state_id, "c": commit},
    )


def _git_head(repo_root: Path) -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_root),
            )
            .decode()
            .strip()
        )
    except Exception:
        return None


def _git_changes(repo_root: Path, since_commit: str) -> list[tuple[str, Path | None, Path | None]]:
    """
    Returns list of (status, old_path, new_path) where status in {'A','M','D','R'}.
    Paths are absolute Path objects rooted at repo_root.
    """
    try:
        out = (
            subprocess.check_output(
                [
                    "git",
                    "diff",
                    "--name-status",
                    "--find-renames",
                    "--diff-filter=AMDR",
                    f"{since_commit}..HEAD",
                    "--",
                    "*.py",
                ],
                cwd=str(repo_root),
            )
            .decode()
            .splitlines()
        )
    except Exception:
        return []

    changes: list[tuple[str, Path | None, Path | None]] = []
    for line in out:
        if not line.strip():
            continue
        parts = line.split("\t")
        tag = parts[0]
        if tag.startswith("R"):  # e.g., R100
            oldp, newp = parts[1], parts[2]
            changes.append(("R", repo_root / oldp, repo_root / newp))
        else:
            st, pth = tag, parts[1]
            if st in ("A", "M"):
                changes.append((st, None, repo_root / pth))
            elif st == "D":
                changes.append((st, repo_root / pth, None))
    return changes


def _all_py_files(repo_root: Path) -> list[Path]:
    return [
        p
        for p in repo_root.rglob("*.py")
        if not any(d in p.parts for d in (".git", ".venv", "__pycache__", "node_modules"))
    ]


# =============================================================================
# ADR loader (frontmatter optional with safe fallback)
# =============================================================================
class _Post:
    def __init__(self, metadata: dict[str, Any], content: str):
        self.metadata = metadata or {}
        self.content = content or ""


def _load_adr_file(adr_path: Path) -> _Post:
    """Load ADR file using python-frontmatter if available, else a minimal YAML-front matter fallback."""
    if frontmatter is not None:
        try:
            fm = frontmatter.load(adr_path)
            return _Post(fm.metadata or {}, fm.content or "")
        except Exception as e:
            logger.warning("frontmatter failed on %s; falling back. err=%s", adr_path, e)

    # Fallback: parse naive YAML block between leading '---' ... '---'
    text = adr_path.read_text(encoding="utf-8", errors="replace")
    meta: dict[str, Any] = {}
    content = text

    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
            fm_text = "\n".join(lines[1:end])
            content = "\n".join(lines[end + 1 :])
            try:
                import yaml  # optional

                meta = yaml.safe_load(fm_text) or {}
            except Exception:
                meta = {}
        except StopIteration:
            # no closing '---' -> treat whole file as content
            pass

    if frontmatter is None:
        logger.warning(
            "ADR parsing running in fallback mode (install python-frontmatter for full support): %s",
            adr_path,
        )
    return _Post(meta, content)


@dataclass
class ResolverConfig:
    current_file_info: dict[str, Any] | None = None
    all_files_cache: dict[str, dict[str, Any]] | None = None
    module_to_file_path: dict[str, str] | None = None
    module_to_defines_global: dict[str, dict[str, str]] | None = None
    repo_root: str | Path | None = None  # optional; not strictly needed but useful for logging


class SymbolResolver:
    """
    Resolve an identifier to either:
      - internal symbol FQN ('internal_symbol')   e.g. '.../codegen.py::JobContext'
      - internal module file path ('internal_module')  (maps to CodeFile.path)
      - external ('external')  (3rd-party/builtin)
      - unknown ('unknown')

    Backwards-compatible constructor:
      - SymbolResolver(config=ResolverConfig(...))
      - SymbolResolver(current_file_info=..., all_files_cache=..., module_to_file_path=..., ...)
      - SymbolResolver()  # (no-arg; safe defaults)
    """

    _ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")

    def __init__(
        self,
        *args,
        config: ResolverConfig | None = None,
        current_file_info: dict[str, Any] | None = None,
        all_files_cache: dict[str, dict[str, Any]] | None = None,
        module_to_file_path: dict[str, str] | None = None,
        module_to_defines_global: dict[str, dict[str, str]] | None = None,
        repo_root: str | Path | None = None,
        **extras: Any,
    ):
        """
        Back-compat rules:
        - Positional legacy order:
            1) current_file_info
            2) all_files_cache
            3) module_to_file_path
            4) module_to_defines_global (optional)
        - Or pass a ResolverConfig via 'config'
        - Or pass explicit kwargs (preferred)
        - Unknown kwargs are kept as attributes for forward-compat
        """
        # Prevent conflicting use of config + explicit kwargs/positional
        if config and (
            args
            or any(
                v is not None
                for v in (
                    current_file_info,
                    all_files_cache,
                    module_to_file_path,
                    module_to_defines_global,
                    repo_root,
                )
            )
        ):
            raise ValueError("Pass either 'config' or positional/keyword fields, not both.")

        # 1) Resolve from config if provided
        if config:
            current_file_info = config.current_file_info
            all_files_cache = config.all_files_cache
            module_to_file_path = config.module_to_file_path
            module_to_defines_global = config.module_to_defines_global
            repo_root = config.repo_root

        # 2) Legacy positional mapping (if args are present)
        #    Expected shapes: (cf, cache, mtp) or (cf, cache, mtp, mdg)
        if args:
            n = len(args)
            if n not in (3, 4):
                raise TypeError(
                    f"SymbolResolver legacy positional args must be 3 or 4, got {n}. "
                    "Expected: (current_file_info, all_files_cache, module_to_file_path[, module_to_defines_global])",
                )
            (cf, cache, mtp, *rest) = args
            mdg = rest[0] if rest else None

            # Only fill from positional if the kwarg wasn’t already provided
            current_file_info = cf if current_file_info is None else current_file_info
            all_files_cache = cache if all_files_cache is None else all_files_cache
            module_to_file_path = mtp if module_to_file_path is None else module_to_file_path
            module_to_defines_global = (
                mdg if module_to_defines_global is None else module_to_defines_global
            )

        # 3) Normalize & defaults
        self.current_file_info: dict[str, Any] = current_file_info or {"imports": {}, "defines": {}}
        self.all_files_cache: dict[str, dict[str, Any]] = all_files_cache or {}
        self.module_to_file_path: dict[str, str] = module_to_file_path or {}
        self.module_to_defines_global: dict[str, dict[str, str]] = module_to_defines_global or {}
        self.repo_root: Path | None = Path(repo_root).resolve() if repo_root else None

        # quick lookup for local defines in this file
        self.local_symbols: dict[str, str] = {
            name: fqn for name, fqn in self.current_file_info.get("defines", {}).items()
        }

        # Store extras (forward-compat)
        for k, v in extras.items():
            setattr(self, k, v)

        # Light validation / diagnostics (don’t crash)
        imports_val = self.current_file_info.get("imports", {})
        if not isinstance(imports_val, dict):
            logger.warning(
                "[SymbolResolver] current_file_info.imports is not a dict; got %r",
                type(imports_val),
            )
        if not isinstance(self.local_symbols, dict):
            logger.warning(
                "[SymbolResolver] current_file_info.defines is not a dict; got %r",
                type(self.current_file_info.get("defines")),
            )

    # -------------------------- core helpers --------------------------

    def _resolve_module_and_symbol(self, module: str, symbol: str) -> tuple[str | None, str]:
        """
        Try local (files touched this run) then fallback to global defines snapshot.
        Returns (FQN, kind)
        """
        # Prefer local cache (files touched this run)
        file_path = self.module_to_file_path.get(module)
        if file_path:
            target_info = self.all_files_cache.get(file_path) or {}
            defs = target_info.get("defines", {}) or {}
            if symbol in defs:
                return defs[symbol], "internal_symbol"

        # Fall back to global graph snapshot (preloaded)
        defs_global = (self.module_to_defines_global or {}).get(module, {}) or {}
        if symbol in defs_global:
            return defs_global[symbol], "internal_symbol"

        return None, "unknown"

    # --------------------------- public API ---------------------------

    def resolve(self, name: str) -> tuple[str | None, str]:
        """
        Resolve a single identifier or dotted reference.
        Returns (target, kind) with kind in {'internal_symbol','internal_module','external','unknown'}
        """

        # 1) Local define in this file (top-level class/func)
        if name in self.local_symbols:
            return self.local_symbols[name], "internal_symbol"

        imports = self.current_file_info.get("imports", {}) or {}

        # 2) Exact import alias (e.g. 'JobContext' when `from ... import JobContext as JobContext`)
        if name in imports:
            full_import = imports[name]
            # (a) Direct module mapping (alias is a module)
            if full_import in self.module_to_file_path:
                return self.module_to_file_path[full_import], "internal_module"
            # (b) alias is a symbol imported from a module -> resolve by module+symbol
            parts = full_import.split(".")
            if len(parts) > 1:
                module_part = ".".join(parts[:-1])
                symbol_part = parts[-1]
                fqn, kind = self._resolve_module_and_symbol(module_part, symbol_part)
                if fqn:
                    return fqn, kind
            # (c) Not ours -> treat as external library root
            return full_import.split(".")[0], "external"

        # 3) Dotted attribute like "alias.symbol" or "alias.subpkg.symbol"
        if "." in name:
            head, tail = name.split(".", 1)  # head = alias/module name, tail = rest
            # Is the head an import alias we recorded?
            if head in imports:
                base_mod = imports[head]  # e.g., "systems.simula.service.services.codegen"
                tail_parts = tail.split(".")
                symbol_part = tail_parts[-1]  # last piece is usually the class/func
                # Try module_part = base_mod or base_mod + ".subpkg..."
                module_part = (
                    base_mod if len(tail_parts) == 1 else base_mod + "." + ".".join(tail_parts[:-1])
                )

                # (i) Try exact module_part
                fqn, kind = self._resolve_module_and_symbol(module_part, symbol_part)
                if fqn:
                    return fqn, kind

                # (ii) Fallback: try just base_mod
                fqn, kind = self._resolve_module_and_symbol(base_mod, symbol_part)
                if fqn:
                    return fqn, kind

                # Not internal -> treat as external package call
                return base_mod.split(".")[0], "external"

        # 4) Builtins count as external (we don't link them)
        if name in BUILTINS:
            return name, "external"

        # 5) Unknown
        return None, "unknown"

    def resolve_all_from_expr(self, expr: str) -> list[str]:
        """
        Extract internal symbol FQNs embedded in an expression, ignoring typing/builtins.
        Example:
          'Optional[codegen.JobContext | None]' -> ['systems/.../codegen.py::JobContext']
        """
        out: list[str] = []
        seen: set[str] = set()
        if not expr:
            return out

        for tok in self._ID_RE.findall(expr):
            if tok in seen:
                continue
            seen.add(tok)
            base = tok.split(".")[0]
            if base in TYPING_WORDS or base in BUILTINS or base == "None":
                continue
            fqn, kind = self.resolve(tok)
            if fqn and kind == "internal_symbol":
                out.append(fqn)
        return out

    # ----------------------- convenience ctor ------------------------

    @classmethod
    def from_maps(
        cls,
        *,
        current_file_info: dict[str, Any] | None = None,
        all_files_cache: dict[str, dict[str, Any]] | None = None,
        module_to_file_path: dict[str, str] | None = None,
        module_to_defines_global: dict[str, dict[str, str]] | None = None,
        repo_root: str | Path | None = None,
    ) -> SymbolResolver:
        return cls(
            current_file_info=current_file_info,
            all_files_cache=all_files_cache,
            module_to_file_path=module_to_file_path,
            module_to_defines_global=module_to_defines_global,
            repo_root=repo_root,
        )


# =============================================================================
# Pass 1: Upsert CodeFile + Code symbols (with embedding hash-gate)
# =============================================================================
async def _pass_one_create_nodes(
    file_path: Path,
    repo_root: Path,
    file_cache: dict[str, dict[str, Any]],
    *,
    force: bool = False,
) -> int:
    """
    Upserts CodeFile + its Code symbols.
    Re-embeds a symbol only if its content hash changed or embedding version changed (unless force=True).
    NOTE: Even when a file is unchanged, we still parse and fill file_cache so
          relationships can be rebuilt for *all* files in pass 2.
    """
    try:
        source_code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code)
    except Exception:
        return 0

    rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
    file_module = _path_to_module(file_path, repo_root)
    file_hash = _hash_text(source_code)

    # Upsert CodeFile by path (keep fqn for backward compatibility)
    await cypher_query(
        f"MERGE (f:{LABEL_CODEFILE} {{path:$path}}) "
        "SET f.module=$module, f.hash=$hash, f.fqn=coalesce(f.fqn,$path), f.updated_at=timestamp()",
        {"path": rel_path, "module": file_module, "hash": file_hash},
    )

    # Preload existing symbols for this file: content_hash + embedding_version
    existing = await cypher_query(
        """
        MATCH (:CodeFile {path:$path})-[:DEFINES]->(c:Code)
        RETURN c.fqn AS fqn,
            c.content_hash AS content_hash,
            coalesce(c.embedding_version,0) AS v,
            c.embedding IS NULL AS missing
        """,
        {"path": rel_path},
    )
    existing_map = {
        row["fqn"]: (row["content_hash"], int(row["v"]), bool(row["missing"])) for row in existing
    }

    # Prepare cache structure for pass-2
    file_info: dict[str, Any] = {
        "path": rel_path,
        "module": file_module,
        "imports": {},
        "defines": {},
        "class_bases": {},
        "function_calls": {},
        "type_hints": {},
    }
    file_cache[rel_path] = file_info

    nodes_upserted = 0

    # Collect imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                file_info["imports"][alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                file_info["imports"][alias.asname or alias.name] = f"{node.module}.{alias.name}"

    # Ensure child->parent links for call collection (best-effort)
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)  # type: ignore

    async def _upsert_symbol(node: ast.AST, kind: str) -> None:
        nonlocal nodes_upserted
        node_fqn = _fqn(file_path, node, relative_to=repo_root)
        src, doc = _node_source_and_doc(node, source_code)
        content_hash = _hash_bytes((src + "\n\n" + doc).encode("utf-8"))

        have = existing_map.get(node_fqn)
        missing_emb = have[2] if have else True
        needs_embed = (
            force
            or (not have)
            or (have[0] != content_hash)
            or (have[1] != EMBEDDING_VERSION)
            or missing_emb
        )

        params = {
            "fqn": node_fqn,
            "name": getattr(node, "name", node_fqn.split("::")[-1]),
            "path": rel_path,
            "doc": doc,
            "src": src,
            "content_hash": content_hash,
            "embed_version": EMBEDDING_VERSION,
            "embed_model": EMBEDDING_MODEL,
        }

        if needs_embed:
            emb = None
            try:
                emb = await get_embedding(
                    src + ("\n\n" + doc if doc else ""), dimensions=VECTOR_DIM
                )
            except Exception:
                emb = None
            params["embedding"] = emb

        set_embedding_clause = ", c.embedding=$embedding" if needs_embed else ""
        query = (
            f"MERGE (c:{LABEL_CODE} {{fqn:$fqn}}) "
            "SET c.name=$name, c.path=$path, c.docstring=$doc, c.source_code=$src, "
            "    c.content_hash=$content_hash, c.embedding_version=$embed_version, c.embedding_model=$embed_model, "
            "    c.updated_at=timestamp()"
            f"{set_embedding_clause} "
            "WITH c "
            f"MATCH (f:{LABEL_CODEFILE} {{path:$path}}) "
            "MERGE (f)-[:DEFINES]->(c)"
        )
        _ = await cypher_query(query, params)
        nodes_upserted += 1

    # Walk top-level defs to capture bases, calls, types
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            file_info["defines"][n.name] = _fqn(file_path, n, relative_to=repo_root)
            await _upsert_symbol(n, "ClassDef")
            # Bases
            bases = []
            for b in n.bases:
                try:
                    bases.append(ast.unparse(b))
                except Exception:
                    pass
            file_info["class_bases"][file_info["defines"][n.name]] = bases

        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            file_info["defines"][n.name] = _fqn(file_path, n, relative_to=repo_root)
            await _upsert_symbol(n, "FunctionDef")

            # Calls (best-effort)
            calls: set[str] = set()
            for sub in ast.walk(n):
                if isinstance(sub, ast.Call):
                    try:
                        calls.add(ast.unparse(sub.func))
                    except Exception:
                        pass
            file_info["function_calls"][file_info["defines"][n.name]] = calls

            # Type hints
            hints: set[str] = set()
            try:
                for arg in getattr(n.args, "args", []):
                    if getattr(arg, "annotation", None) is not None:
                        hints.add(ast.unparse(arg.annotation))
                if getattr(n.args, "posonlyargs", None):
                    for arg in n.args.posonlyargs:
                        if getattr(arg, "annotation", None) is not None:
                            hints.add(ast.unparse(arg.annotation))
                if getattr(n.args, "kwonlyargs", None):
                    for arg in n.args.kwonlyargs:
                        if getattr(arg, "annotation", None) is not None:
                            hints.add(ast.unparse(arg.annotation))
                if getattr(n, "returns", None) is not None:
                    hints.add(ast.unparse(n.returns))
            except Exception:
                pass
            file_info["type_hints"][file_info["defines"][n.name]] = hints

    return nodes_upserted


# =============================================================================
# Pass 2: Relationships (clear & rebuild for selected files)
# =============================================================================
async def _clear_outgoing_rels_for_file(rel_path: str) -> None:
    # Remove file-level IMPORTS and symbol-level rels for this file
    await cypher_query(
        f"""
        MATCH (f:{LABEL_CODEFILE} {{path:$path}})
        OPTIONAL MATCH (f)-[r1:IMPORTS]->() DELETE r1
        WITH f
        MATCH (f)-[:DEFINES]->(c:{LABEL_CODE})
        OPTIONAL MATCH (c)-[r:CALLS|INHERITS_FROM|USES_TYPE]->() DELETE r
        """,
        {"path": rel_path},
    )


async def _delete_file_graph(rel_path: str) -> None:
    """Remove a CodeFile and its defined Code symbols (and their incident rels)."""
    await cypher_query(
        f"""
        MATCH (f:{LABEL_CODEFILE} {{path:$path}})
        OPTIONAL MATCH (f)-[:DEFINES]->(c:{LABEL_CODE})
        DETACH DELETE f, c
        """,
        {"path": rel_path},
    )


async def _pass_two_create_relationships(
    file_key: str,  # rel_path string used as key in file_cache
    file_cache: dict[str, dict[str, Any]],
    module_to_file_path: dict[str, str],
    module_to_defines_global: dict[str, dict[str, str]] | None = None,
) -> int:
    file_info = file_cache[file_key]
    resolver = SymbolResolver(
        file_info,
        file_cache,
        module_to_file_path,
        module_to_defines_global=module_to_defines_global,
    )
    rels_created = 0

    # IMPORTS (file -> file or file -> Library)
    for alias, full_import in file_info["imports"].items():
        target, kind = resolver.resolve(alias)
        if kind == "internal_module" and target:
            # CodeFile -> CodeFile
            await cypher_query(
                f"""
                MATCH (src:{LABEL_CODEFILE} {{path:$src}}), (dst:{LABEL_CODEFILE} {{path:$dst}})
                MERGE (src)-[:IMPORTS]->(dst)
                """,
                {"src": file_info["path"], "dst": target},
            )
            rels_created += 1
        elif kind == "external" and target and target not in STD_LIBS:
            await cypher_query("MERGE (l:Library {name:$name})", {"name": target})
            await cypher_query(
                f"""
                MATCH (src:{LABEL_CODEFILE} {{path:$src}}), (l:Library {{name:$name}})
                MERGE (src)-[:IMPORTS]->(l)
                """,
                {"src": file_info["path"], "name": target},
            )
            rels_created += 1

    # INHERITS_FROM (class -> base class)
    for class_fqn, base_names in file_info.get("class_bases", {}).items():
        for base in base_names:
            target, kind = resolver.resolve(base)
            if target and kind == "internal_symbol":
                await cypher_query(
                    f"""
                    MATCH (src:{LABEL_CODE} {{fqn:$src}}), (dst:{LABEL_CODE} {{fqn:$dst}})
                    MERGE (src)-[:INHERITS_FROM]->(dst)
                    """,
                    {"src": class_fqn, "dst": target},
                )
                rels_created += 1

    # CALLS (func -> symbol), dotted names supported
    for func_fqn, call_names in file_info.get("function_calls", {}).items():
        for call_name in call_names:
            target, kind = resolver.resolve(call_name)
            if target and kind == "internal_symbol":
                await cypher_query(
                    f"""
                    MATCH (src:{LABEL_CODE} {{fqn:$src}}), (dst:{LABEL_CODE} {{fqn:$dst}})
                    MERGE (src)-[:CALLS]->(dst)
                    """,
                    {"src": func_fqn, "dst": target},
                )
                rels_created += 1

    # USES_TYPE (func -> type symbol), handle generics / unions
    for func_fqn, hint_names in file_info.get("type_hints", {}).items():
        for hint in hint_names:
            for dst_fqn in resolver.resolve_all_from_expr(hint):
                await cypher_query(
                    f"""
                    MATCH (src:{LABEL_CODE} {{fqn:$src}}), (dst:{LABEL_CODE} {{fqn:$dst}})
                    MERGE (src)-[:USES_TYPE]->(dst)
                    """,
                    {"src": func_fqn, "dst": dst_fqn},
                )
                rels_created += 1

    return rels_created


# =============================================================================
# Pass 3: ADR ingest (incremental)
# =============================================================================
async def _pass_three_ingest_adrs_incremental(repo_root: Path, *, force: bool = False) -> int:
    nodes_upserted = 0
    for adr_path in repo_root.glob(ADR_GLOB):
        try:
            post = _load_adr_file(adr_path)

            title = post.metadata.get("title") or adr_path.stem
            status = post.metadata.get("status", "unknown")
            related_paths = post.metadata.get("related_code", []) or []

            rel_path = str(adr_path.relative_to(repo_root)).replace("\\", "/")
            content = post.content
            content_hash = _hash_text(f"{content}\n\n{title}\n{status}")

            # Check existing hash/version
            have = await cypher_query(
                """
                MATCH (a:ArchitecturalDecision {path:$path})
                RETURN a.content_hash AS h, coalesce(a.embedding_version,0) AS v
                """,
                {"path": rel_path},
            )
            have_hash = have[0]["h"] if have else None
            have_ver = int(have[0]["v"]) if have and have[0].get("v") is not None else 0

            needs_embed = force or (have_hash != content_hash) or (have_ver != EMBEDDING_VERSION)

            params = {
                "path": rel_path,
                "title": title,
                "status": status,
                "content": content,
                "content_hash": content_hash,
                "embed_version": EMBEDDING_VERSION,
                "embed_model": EMBEDDING_MODEL,
            }
            if needs_embed:
                emb = None
                try:
                    emb = await get_embedding(
                        f"ADR: {title}\nStatus: {status}\n\n{content}",
                        dimensions=VECTOR_DIM,
                    )
                except Exception:
                    emb = None
                params["embedding"] = emb

            set_emb = ", a.embedding=$embedding" if needs_embed else ""
            await cypher_query(
                f"""
                MERGE (a:ArchitecturalDecision {{path:$path}})
                SET a.title=$title, a.status=$status, a.content=$content,
                    a.content_hash=$content_hash, a.embedding_version=$embed_version,
                    a.embedding_model=$embed_model, a.updated_at=timestamp(){set_emb}
                """,
                params,
            )
            nodes_upserted += 1

            # Link ADR -> CodeFile for any declared related paths
            if related_paths:
                await cypher_query(
                    f"""
                    UNWIND $rels AS code_path
                    MATCH (a:ArchitecturalDecision {{path:$adr}}), (c:{LABEL_CODEFILE} {{path: code_path}})
                    MERGE (a)-[:DOCUMENTS]->(c)
                    """,
                    {"adr": rel_path, "rels": related_paths},
                )

        except Exception as e:
            logger.exception("ADR ingest failed for %s: %s", adr_path, e)
            continue
    return nodes_upserted


# =============================================================================
# Orchestrator
# =============================================================================
async def patrol_and_ingest(
    root_dir: str = ".",
    *,
    force: bool = False,
    changed_only: bool = True,
    dry_run: bool = False,
    state_id: str | None = None,
) -> dict[str, Any]:
    """
    Main entry point.
    - If Git available and changed_only=True, only process files changed since last successful run
      (but we still parse *all* candidate files to rebuild relationships).
    - Within each file, only re-embed symbols whose content changed (or embedding version bumped) unless force=True.
    - Relationships are rebuilt for every file parsed this run.
    """
    repo_root = Path(root_dir).resolve()
    state = state_id or os.getenv("QORA_INGEST_STATE_ID", "default")

    # Ensure indices/constraints
    from .schema import ensure_all_graph_indices

    try:
        await ensure_all_graph_indices()
    except Exception:
        pass

    total_nodes, total_rels, adr_nodes = 0, 0, 0
    files_processed = 0

    head = _git_head(repo_root)
    last = await _get_last_commit_from_graph(state) if head else None

    candidates: set[Path] = set()

    if head and last and not force and changed_only:
        # normal commit-to-commit diff
        changes = _git_changes(repo_root, last)
        dels = 0
        for st, oldp, newp in changes:
            if st == "D" and oldp:
                rel = str(oldp.relative_to(repo_root)).replace("\\", "/")
                await _delete_file_graph(rel)
                dels += 1
            elif st == "R" and oldp and newp:
                rel_old = str(oldp.relative_to(repo_root)).replace("\\", "/")
                await _delete_file_graph(rel_old)
                candidates.add(newp)
            elif st in ("A", "M") and newp:
                candidates.add(newp)

        # Consider uncommitted edits if diff is empty
        if not candidates and dels == 0:
            for st, oldp, newp in _git_worktree_changes(repo_root):
                if st == "D" and oldp:
                    rel = str(oldp.relative_to(repo_root)).replace("\\", "/")
                    await _delete_file_graph(rel)
                elif st in ("A", "M", "R") and newp:
                    candidates.add(newp)

        if not candidates:
            candidates = set(_all_py_files(repo_root))
    else:
        candidates = set(_all_py_files(repo_root))

    # ---------- PASS 1: upsert nodes (and ALWAYS fill file_cache) ----------
    file_cache: dict[str, dict[str, Any]] = {}
    for file_path in sorted(candidates):
        up = await _pass_one_create_nodes(file_path, repo_root, file_cache, force=force)
        if up > 0:
            total_nodes += up
            files_processed += 1
        else:
            # unchanged file still parsed and placed in file_cache (so we can rebuild relationships)
            files_processed += 1

    # Build GLOBAL lookups from graph (module -> path, and module -> {name->fqn})
    # so we can resolve symbols across files we didn't touch.
    mod_rows = await cypher_query("MATCH (f:CodeFile) RETURN f.module AS module, f.path AS path")
    module_to_file_path_global = {
        r["module"]: r["path"] for r in mod_rows if r.get("module") and r.get("path")
    }
    def_rows = await cypher_query(
        "MATCH (f:CodeFile)-[:DEFINES]->(c:Code) RETURN f.module AS module, c.name AS name, c.fqn AS fqn",
    )
    module_to_defines_global: dict[str, dict[str, str]] = {}
    for r in def_rows:
        mod = r.get("module")
        nm = r.get("name")
        fq = r.get("fqn")
        if not (mod and nm and fq):
            continue
        module_to_defines_global.setdefault(mod, {})[nm] = fq

    # Merge local modules (from this run) over global mapping (local wins)
    module_to_file_path_local = {info["module"]: key for key, info in file_cache.items()}
    module_to_file_path = {**module_to_file_path_global, **module_to_file_path_local}

    # ---------- PASS 2: clear/rebuild relationships for ALL files we parsed ----------
    for file_key in list(file_cache.keys()):
        await _clear_outgoing_rels_for_file(file_key)
        rels = await _pass_two_create_relationships(
            file_key,
            file_cache,
            module_to_file_path,
            module_to_defines_global=module_to_defines_global,
        )
        total_rels += rels

    # PASS 3: ADRs (incremental)
    adr_nodes = await _pass_three_ingest_adrs_incremental(repo_root, force=force)
    total_nodes += adr_nodes

    if head and not dry_run:
        await _set_last_commit_in_graph(head, state)

    return {
        "ok": True,
        "files_processed": files_processed,
        "nodes_upserted": total_nodes,
        "rels_created": total_rels,
        "adrs_ingested": adr_nodes,
        "mode": "force_full" if force else ("changed_only" if changed_only else "full_scan"),
        "head": head,
        "since": last,
        "state_id": state,
    }


# touch
