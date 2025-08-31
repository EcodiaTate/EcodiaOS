# systems/simula/code_sim/impact/py_callgraph.py
from __future__ import annotations

import ast
from pathlib import Path


def build_callgraph(root: str = ".") -> dict[str, set[str]]:
    """
    Approximate callgraph mapping function name -> set(callees) within the project.
    """
    cg: dict[str, set[str]] = {}
    files = [p for p in Path(root).rglob("**/*.py") if "/tests/" not in str(p)]
    for p in files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        funcs: list[str] = []
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                funcs.append(n.name)
                cg.setdefault(n.name, set())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                for f in funcs:
                    # naive: attribute calls ignored
                    cg.setdefault(f, set())
                # link all funcs in this file to called name
                for f in funcs:
                    cg[f].add(n.func.id)
    return cg
