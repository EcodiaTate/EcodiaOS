# systems/simula/policy/effects.py
# NEW FILE FOR PHASE III
from __future__ import annotations

import ast

DANGEROUS_CALLS = {"os.system", "subprocess.run", "eval", "exec"}
NETWORK_MODULES = {"requests", "httpx", "socket", "urllib"}


class EffectAnalyzer(ast.NodeVisitor):
    """Analyzes a Python AST to infer potential side-effects."""

    def __init__(self):
        self.effects: set[str] = set()
        self.net_access: bool = False
        self.execution: bool = False

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in NETWORK_MODULES:
                self.net_access = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module in NETWORK_MODULES:
            self.net_access = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func_name = ast.unparse(node.func)
        if func_name in DANGEROUS_CALLS:
            self.execution = True
        self.generic_visit(node)


def extract_effects_from_diff(diff_text: str) -> dict[str, bool]:
    """
    Performs static analysis on the Python code added in a diff to infer side-effects.
    """
    added_code_lines = [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]

    if not added_code_lines:
        return {}

    try:
        tree = ast.parse("\n".join(added_code_lines))
        analyzer = EffectAnalyzer()
        analyzer.visit(tree)
        return {
            "net_access": analyzer.net_access,
            "execution": analyzer.execution,
        }
    except SyntaxError:
        # If the diff is not valid Python, we can't analyze it.
        return {"execution": True}  # Fail safe: assume execution if unparseable
