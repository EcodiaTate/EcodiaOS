# systems/simula/code_sim/evaluators/impact.py
from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from core.utils.diff import changed_paths_from_unified_diff


@dataclass
class ImpactReport:
    changed: list[str]
    candidate_tests: list[str]
    k_expr: str  # pytest -k expression focusing on impacted scopes


def _iter_tests(root: Path) -> Iterable[Path]:
    for p in root.rglob("test_*.py"):
        yield p
    for p in root.rglob("*_test.py"):
        yield p


def _module_name_from_path(p: Path) -> str:
    # turn "pkg/foo/bar.py" → "pkg.foo.bar"
    rel = p.as_posix().rstrip(".py")
    if rel.endswith(".py"):
        rel = rel[:-3]
    return rel.replace("/", ".").lstrip(".")


def _collect_imports(p: Path) -> set[str]:
    out: set[str] = set()
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception:
        return out
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                out.add(n.module)
    return out


def _likely_test_for_module(mod_name: str, tests_root: Path) -> list[str]:
    # Heuristics:
    # 1) direct file mapping: tests/test_<leaf>.py
    # 2) any test file importing the module or its parent package
    candidates: set[str] = set()

    leaf = mod_name.split(".")[-1]
    for pattern in [f"test_{leaf}.py", f"{leaf}_test.py"]:
        for p in tests_root.rglob(pattern):
            candidates.add(p.as_posix())

    # import-based matching
    wanted = {mod_name}
    # include parent packages (pkg.foo.bar -> pkg.foo, pkg)
    parts = mod_name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        wanted.add(".".join(parts[:i]))

    for p in _iter_tests(tests_root):
        imps = _collect_imports(p)
        if any(w in imps for w in wanted):
            candidates.add(p.as_posix())

    return sorted(candidates)


def _nodeids_from_files(files: list[str]) -> list[str]:
    # Pytest nodeids can just be file paths; -k uses substrings, so we return base filenames too
    ids: set[str] = set()
    for f in files:
        ids.add(f)
        ids.add(Path(f).stem)  # helps -k match
    return sorted(ids)


def compute_impact(diff_text: str, *, workspace_root: str = ".") -> ImpactReport:
    """
    Map a unified diff to an impact-focused test selection.
    Returns test file candidates and a `-k` expression for pytest.
    """
    changed = [p for p in changed_paths_from_unified_diff(diff_text) if p.endswith(".py")]
    if not changed:
        return ImpactReport(changed=[], candidate_tests=[], k_expr="")

    root = Path(workspace_root).resolve()
    tests_root = root / "tests"
    mods = []
    for c in changed:
        p = (root / c).resolve()
        if not p.exists():
            # infer module name from path anyway
            mods.append(_module_name_from_path(Path(c)))
        else:
            mods.append(_module_name_from_path(p.relative_to(root)))

    test_files: set[str] = set()
    if tests_root.exists():
        for m in mods:
            for t in _likely_test_for_module(m, tests_root):
                test_files.add(t)

    # fallbacks: if nothing matched, run whole tests dir
    if not test_files and tests_root.exists():
        for p in _iter_tests(tests_root):
            test_files.add(p.as_posix())

    nodeids = _nodeids_from_files(sorted(test_files))
    # Pytest -k expression prefers OR of stems to keep it short
    # cap to avoid CLI explosion
    stems = [Path(n).stem for n in nodeids if n.endswith(".py")]
    stems = stems[:24] if len(stems) > 24 else stems
    k_expr = " or ".join(sorted(set(stems)))

    return ImpactReport(changed=changed, candidate_tests=sorted(test_files), k_expr=k_expr)
