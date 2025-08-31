# systems/simula/code_sim/portfolio/strategies_structural.py
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


def _read_text(p: str) -> str:
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def _unified(before: str, after: str, path: str) -> str:
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}", n=2))


def _extract_function(src: str, fn: str) -> tuple[str | None, tuple[int, int] | None]:
    try:
        t = ast.parse(src)
    except Exception:
        return None, None
    for n in t.body:
        if isinstance(n, ast.FunctionDef) and n.name == fn:
            start = n.lineno - 1
            end = getattr(n, "end_lineno", None)
            if not end:
                # fallback: scan until next top-level def/class
                end = start + 1
                lines = src.splitlines()
                while end < len(lines) and not lines[end].startswith(("def ", "class ")):
                    end += 1
            return src.splitlines()[start:end], (start, end)
    return None, None


def _extract_function_to_module(src: str, fn: str, new_module: str) -> str | None:
    lines = src.splitlines()
    body, span = _extract_function(src, fn)
    if not body or not span:
        return None
    start, end = span
    # naive extraction: keep function, add import of new module and call-through
    "\n".join(body)
    call_through = f"\n\n# Simula extracted {fn} to {new_module}\nfrom {new_module} import {fn}  # type: ignore\n"
    new_src = "\n".join(lines[:start]) + call_through + "\n".join(lines[end:])
    return new_src


def _rename_function(src: str, old: str, new: str) -> str | None:
    try:
        t = ast.parse(src)
    except Exception:
        return None

    class Ren(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name == old:
                node.name = new
            return self.generic_visit(node)

        def visit_Call(self, node: ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == old:
                node.func.id = new
            return self.generic_visit(node)

    new = Ren().visit(t)
    ast.fix_missing_locations(new)
    return ast.unparse(new) if hasattr(ast, "unparse") else None


def _tighten_signature(src: str, fn: str) -> str | None:
    try:
        t = ast.parse(src)
    except Exception:
        return None

    class Tight(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name != fn:
                return node
            # add Optional[...] type hints if missing
            for a in node.args.args:
                if a.annotation is None and a.arg not in ("self", "cls"):
                    a.annotation = ast.Name(id="object")
            if node.returns is None:
                node.returns = ast.Name(id="object")
            return node

    new = Tight().visit(t)
    ast.fix_missing_locations(new)
    return ast.unparse(new) if hasattr(ast, "unparse") else None


def generate_structural_candidates(
    target_file: str,
    fn_name: str | None,
) -> list[CandidatePatch]:
    before = _read_text(target_file)
    if not before:
        return []

    cands: list[CandidatePatch] = []

    if fn_name:
        # 1) Rename function (safe adapter will be needed by tests)
        renamed = _rename_function(before, fn_name, f"{fn_name}_impl")
        if renamed and renamed != before:
            cands.append(
                CandidatePatch(
                    uid="rename-fn",
                    rationale=f"Rename {fn_name}→{fn_name}_impl to enable adapter injection.",
                    risk="medium",
                    diff=_unified(before, renamed, target_file),
                    meta={"strategy": "rename_function", "fn": fn_name},
                ),
            )

        # 2) Tighten signature
        typed = _tighten_signature(before, fn_name)
        if typed and typed != before:
            cands.append(
                CandidatePatch(
                    uid="tighten-signature",
                    rationale=f"Add type hints to {fn_name} to clarify contracts.",
                    risk="low",
                    diff=_unified(before, typed, target_file),
                    meta={"strategy": "tighten_signature", "fn": fn_name},
                ),
            )

        # 3) Extract to module (call-through)
        modex = _extract_function_to_module(before, fn_name, f"{Path(target_file).stem}_impl")
        if modex and modex != before:
            cands.append(
                CandidatePatch(
                    uid="extract-module",
                    rationale=f"Extract {fn_name} into companion module; original calls through.",
                    risk="high",
                    diff=_unified(before, modex, target_file),
                    meta={"strategy": "extract_module", "fn": fn_name},
                ),
            )

    return cands[:6]
