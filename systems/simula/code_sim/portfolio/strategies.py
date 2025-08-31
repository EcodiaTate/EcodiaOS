# systems/simula/code_sim/portfolio/strategies.py
from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CandidatePatch:
    uid: str
    rationale: str
    risk: str  # "low" | "medium" | "high"
    diff: str
    meta: dict[str, Any]


def _read(path: str) -> tuple[str, ast.AST | None]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception:
        return "", None
    try:
        return text, ast.parse(text)
    except Exception:
        return text, None


def _unified(before: str, after: str, path: str) -> str:
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}", n=2))


def _insert_guard_none(src: str, fn_name: str) -> str | None:
    try:
        tree = ast.parse(src)
    except Exception:
        return None

    class Rewriter(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name != fn_name:
                return node
            guards = []
            for arg in node.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                guards.append(ast.parse(f"if {arg.arg} is None:\n    return {arg.arg}").body[0])
            node.body = guards + node.body
            return node

    try:
        new = Rewriter().visit(tree)
        ast.fix_missing_locations(new)

        return ast.unparse(new) if hasattr(ast, "unparse") else None
    except Exception:
        return None


def _insert_logging(src: str, fn_name: str) -> str | None:
    # naive: add `import logging` (if absent) and a log line at top of function
    if "import logging" not in src:
        src = "import logging\n" + src
    try:
        tree = ast.parse(src)
    except Exception:
        return None

    class Rewriter(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name != fn_name:
                return node
            log = ast.parse(f'logging.debug("Simula:{fn_name} called")').body[0]
            node.body = [log] + node.body
            return node

    try:
        new = Rewriter().visit(tree)
        ast.fix_missing_locations(new)
        return ast.unparse(new) if hasattr(ast, "unparse") else None
    except Exception:
        return None


def _docstring_update(src: str, fn_name: str, note: str) -> str | None:
    try:
        tree = ast.parse(src)
    except Exception:
        return None

    class Rewriter(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name != fn_name:
                return node
            doc = ast.get_docstring(node)
            new_doc = (doc or "") + f"\n\nSimula: {note}"
            node.body.insert(0, ast.parse(f'"""%s"""' % new_doc).body[0])
            return node

    try:
        new = Rewriter().visit(tree)
        ast.fix_missing_locations(new)
        return ast.unparse(new) if hasattr(ast, "unparse") else None
    except Exception:
        return None


def generate_candidates(
    target_file: str,
    fn_name: str | None,
    *,
    intent: str,
) -> list[CandidatePatch]:
    before, _ = _read(target_file)
    if not before:
        return []

    cands: list[CandidatePatch] = []

    # Low-risk: docstring augmentation (acceptance/contract hint)
    if fn_name:
        after = _docstring_update(before, fn_name, f"intent={intent}")
        if after and after != before:
            cands.append(
                CandidatePatch(
                    uid="doc-hint",
                    rationale="Clarify contract via docstring to anchor acceptance/specs.",
                    risk="low",
                    diff=_unified(before, after, target_file),
                    meta={"strategy": "docstring_hint", "fn": fn_name},
                ),
            )

    # Medium: None-guard on parameters
    if fn_name:
        after = _insert_guard_none(before, fn_name)
        if after and after != before:
            cands.append(
                CandidatePatch(
                    uid="guard-none",
                    rationale="Add None-guards to function parameters to avoid TypeErrors.",
                    risk="medium",
                    diff=_unified(before, after, target_file),
                    meta={"strategy": "guard_none", "fn": fn_name},
                ),
            )

    # Medium: lightweight logging
    if fn_name:
        after = _insert_logging(before, fn_name)
        if after and after != before:
            cands.append(
                CandidatePatch(
                    uid="log-entry",
                    rationale="Add debug log on function entry to aid observability in large repos.",
                    risk="low",
                    diff=_unified(before, after, target_file),
                    meta={"strategy": "log_entry", "fn": fn_name},
                ),
            )

    # Fallback: whitespace/pep8 normalization (no-op safety)
    if not cands:
        if not before.endswith("\n"):
            after = before + "\n"
            cands.append(
                CandidatePatch(
                    uid="newline-eof",
                    rationale="Ensure newline at EOF.",
                    risk="low",
                    diff=_unified(before, after, target_file),
                    meta={"strategy": "formatting"},
                ),
            )

    return cands[:6]
