# systems/simula/code_sim/mutation/mutants.py
from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mutant:
    file: str
    before: str
    after: str
    label: str


_REWRS = [
    # Boolean negation
    (
        ast.UnaryOp,
        ast.Not,
        lambda n: ast.copy_location(ast.UnaryOp(op=ast.Not(), operand=n.operand), n),
    ),
    # Compare operators swap
    (ast.Gt, None, lambda n: ast.Lt()),
    (ast.Lt, None, lambda n: ast.Gt()),
    (ast.GtE, None, lambda n: ast.LtE()),
    (ast.LtE, None, lambda n: ast.GtE()),
    # True/False flip
    (
        ast.Constant,
        True,
        lambda n: ast.copy_location(ast.Constant(value=not n.value), n)
        if isinstance(n.value, bool)
        else n,
    ),
]


def _mutate(tree: ast.AST) -> list[tuple[str, ast.AST]]:
    out = []

    class Rewriter(ast.NodeTransformer):
        def visit(self, node):  # type: ignore
            for typ, mark, fn in _REWRS:
                try:
                    if (
                        typ is ast.Constant
                        and isinstance(node, ast.Constant)
                        and isinstance(node.value, bool)
                    ) or (
                        isinstance(node, typ)
                        and (mark is None or isinstance(getattr(node, "op", None), mark))
                    ):
                        new = fn(node)
                        if new is not node:
                            out.append((f"{typ.__name__}", new))
                except Exception:
                    pass
            return self.generic_visit(node)

    Rewriter().visit(tree)
    return [(lbl, t) for (lbl, t) in out]


def _unified(before: str, after: str, path: str) -> str:
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}", n=2))


def generate_mutants(py_file: str, *, max_per_file: int = 8) -> list[Mutant]:
    p = Path(py_file)
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return []
    try:
        tree = ast.parse(text)
    except Exception:
        return []
    muts = _mutate(tree)[:max_per_file]
    out: list[Mutant] = []
    for i, (lbl, _newnode) in enumerate(muts):
        # naive: replace first occurrence only by toggling booleans in text positions
        after = (
            text.replace(" True", " False").replace(" False", " True")
            if "Constant" in lbl
            else text
        )
        if after != text:
            out.append(Mutant(file=str(p), before=text, after=after, label=lbl))
            break
    return out
