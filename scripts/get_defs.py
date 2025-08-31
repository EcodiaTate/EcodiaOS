#!/usr/bin/env python3
"""
Collate definition headers across EcodiaOS.

Finds, in all *.py files under the given roots:
  - function / async function definition lines (first line only)
  - class definition lines (first line only)
  - router/app assignment lines (e.g., `router = APIRouter(...)`, `app = FastAPI(...)`)

Usage:
  python collate_defs.py
  python collate_defs.py --out D:\\EcodiaOS\\definitions_collated.txt
  python collate_defs.py --roots D:\\EcodiaOS\\core D:\\EcodiaOS\api D:\\EcodiaOS\\systems
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

DEFAULT_ROOTS = [
    r"D:\EcodiaOS\core",
    r"D:\EcodiaOS\api",
]

SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".tox",
    "node_modules",
    "venv",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
}

# Regex fallbacks for when AST parse fails or to catch wrapped router/app patterns
RE_DEF_LINE = re.compile(r"^\s*(?:async\s+def|def|class)\s+\w+", re.UNICODE)
RE_ROUTER_APP_SIMPLE = re.compile(
    r"""^\s*
        (?P<var>router|app)          # target
        \s*=\s*
        .{0,60}?                      # allow wrapper start
        (?:\b(?:APIRouter|FastAPI|Starlette|Router|NinjaAPI)\b)  # ctor
        \s*\(
    """,
    re.VERBOSE,
)


def read_text(path: Path) -> str | None:
    # Try utf-8 first; degrade gracefully to replacement
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            return None
    except Exception:
        return None


def call_name(n: ast.AST) -> str | None:
    """Return the final identifier of a call: APIRouter, FastAPI, fastapi.FastAPI -> FastAPI."""
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        return n.attr
    return None


ROUTER_APP_CTORS = {"APIRouter", "FastAPI", "Starlette", "Router", "NinjaAPI"}


def find_router_app_lines(tree: ast.AST, lines: list[str]) -> set[int]:
    """Find line numbers of assignments like router=APIRouter(...), app=FastAPI(...)."""
    linenos: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            # Check targets include Name('router'|'app')
            target_names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if not target_names & {"router", "app"}:
                continue
            # Value must be a Call or wrapped Call; check top-level and first arg
            val = node.value
            candidates: list[ast.Call] = []
            if isinstance(val, ast.Call):
                candidates.append(val)
                # If wrapper like SomeWrapper(APIRouter(...)), inspect args for Call
                for arg in val.args[:2]:
                    if isinstance(arg, ast.Call):
                        candidates.append(arg)
            # Identify ctor name in candidates
            found = any(call_name(c.func) in ROUTER_APP_CTORS for c in candidates)
            if found and hasattr(node, "lineno"):
                linenos.add(node.lineno)
    # Fallback regex for any missed wrapped forms
    for i, line in enumerate(lines, start=1):
        if RE_ROUTER_APP_SIMPLE.match(line):
            linenos.add(i)
    return linenos


def gather_defs_from_file(path: Path) -> list[tuple[int, str]]:
    """
    Return list of (lineno, line_text) for def/class/router/app lines in a file.
    """
    text = read_text(path)
    if text is None:
        return []
    lines = text.splitlines()
    line_hits: set[int] = set()

    # Parse with AST for precise def/class detection
    tree = None
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            # Function / AsyncFunction / Class first-line lineno
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                if hasattr(node, "lineno"):
                    line_hits.add(node.lineno)
        # Router/app assignments
        line_hits |= find_router_app_lines(tree, lines)
    else:
        # Fallback: regex scan for def/class and router/app
        for i, line in enumerate(lines, start=1):
            if RE_DEF_LINE.match(line) or RE_ROUTER_APP_SIMPLE.match(line):
                line_hits.add(i)

    # Extract exact source line (first line only)
    results = []
    for ln in sorted(line_hits):
        # Guard against out of range
        if 1 <= ln <= len(lines):
            raw = lines[ln - 1].rstrip()
            # Keep only the leading portion up to a trailing ":" if present on that line,
            # otherwise emit the line as-is
            results.append((ln, raw))
    return results


def iter_python_files(root: Path) -> Iterable[Path]:
    # Manual walk to skip SKIP_DIRS efficiently on Windows
    for dirpath, dirnames, filenames in os.walk(root):
        # prune directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def collate(roots: list[Path]) -> str:
    out = io.StringIO()
    for root in roots:
        if not root.exists():
            continue
        for f in sorted(iter_python_files(root)):
            defs = gather_defs_from_file(f)
            if not defs:
                continue
            out.write(f"### {f}\n")
            for ln, line in defs:
                out.write(f"{line}\n")
            out.write("\n")
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(
        description="Collate function/class/router/app definitions across EcodiaOS.",
    )
    parser.add_argument(
        "--roots",
        nargs="+",
        default=DEFAULT_ROOTS,
        help="Root directories to scan (default: D:\\EcodiaOS\\core D:\\EcodiaOS\\api D:\\EcodiaOS\\systems)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output file path. If omitted, prints to stdout.",
    )
    args = parser.parse_args()

    roots = [Path(r) for r in args.roots]
    payload = collate(roots)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
