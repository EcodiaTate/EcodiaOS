# systems/simula/code_sim/impact/scope_map.py
from __future__ import annotations

import ast
from pathlib import Path


def map_symbols_to_tests(root: str = ".") -> dict[str, set[str]]:
    """
    Heuristic map: if a test file imports module X, we map X to that test file.
    """
    rootp = Path(root)
    mod_to_tests: dict[str, set[str]] = {}
    tests: list[Path] = []
    for p in rootp.rglob("tests/**/*.py"):
        tests.append(p)
    for p in rootp.rglob("**/*.py"):
        if "/tests/" in str(p.as_posix()):
            continue
        try:
            ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        mod = p.as_posix().replace("/", ".")[:-3]
        mod_to_tests.setdefault(mod, set())
        for tp in tests:
            try:
                ttree = ast.parse(tp.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            for n in ast.walk(ttree):
                if (
                    isinstance(n, ast.ImportFrom)
                    and n.module
                    and n.module in (mod, mod.rsplit(".", 1)[0])
                ):
                    mod_to_tests[mod].add(tp.as_posix())
                if isinstance(n, ast.Import):
                    for nm in n.names:
                        if nm.name in (mod, mod.rsplit(".", 1)[0]):
                            mod_to_tests[mod].add(tp.as_posix())
    return mod_to_tests
