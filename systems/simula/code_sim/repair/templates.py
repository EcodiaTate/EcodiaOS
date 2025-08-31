# systems/simula/code_sim/repair/templates.py
# --- PROJECT SENTINEL UPGRADE (FINAL) ---
from __future__ import annotations

import ast
from dataclasses import dataclass

# We now use LibCST for robust, syntax-aware transformations.
import libcst as cst
import libcst.matchers as m
from libcst.codemod import CodemodContext, VisitorBasedCodemodCommand


@dataclass
class Patch:
    path: str
    before: str
    after: str
    transform_id: str


class GuardNoneTransformer(VisitorBasedCodemodCommand):
    """
    An AST-based transformer that adds 'if x is None: return None' guards
    to the beginning of functions for non-self/cls parameters.
    """

    def __init__(self, context: CodemodContext) -> None:
        super().__init__(context)

    def leave_FunctionDef(
        self,
        original_node: cst.FunctionDef,
        updated_node: cst.FunctionDef,
    ) -> cst.FunctionDef:
        guards = []
        # Find parameters that are not 'self' or 'cls' and have no default value
        for param in updated_node.params.params:
            if param.name.value not in ("self", "cls") and param.default is None:
                guard_statement = cst.parse_statement(f"if {param.name.value} is None: return None")
                guards.append(guard_statement)

        # Insert guards after the docstring (if any)
        body_statements = list(updated_node.body.body)
        insert_pos = (
            1
            if (
                body_statements
                and m.matches(
                    body_statements[0],
                    m.SimpleStatementLine(body=[m.Expr(value=m.SimpleString())]),
                )
            )
            else 0
        )

        new_body_statements = body_statements[:insert_pos] + guards + body_statements[insert_pos:]
        return updated_node.with_changes(
            body=updated_node.body.with_changes(body=new_body_statements),
        )


class ImportFixTransformer(VisitorBasedCodemodCommand):
    """
    An AST-based transformer that finds and adds common missing imports.
    This is a placeholder for a more sophisticated import resolver.
    """

    def __init__(self, context: CodemodContext) -> None:
        super().__init__(context)
        self.found_any = False
        self.needs_typing_import = False

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        # Check for un-imported but common type hints
        if "Optional" in ast.unparse(node.returns) or any(
            "Optional" in ast.unparse(p.annotation) for p in node.params.params if p.annotation
        ):
            self.needs_typing_import = True

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        if self.needs_typing_import:
            # This is a simple version; a full implementation would check existing imports
            typing_import = cst.parse_statement("from typing import Any, Dict, List, Optional")
            new_body = [typing_import] + list(updated_node.body)
            return updated_node.with_changes(body=new_body)
        return updated_node


# The list of transforms to apply in order.
TRANSFORMS: list[tuple[str, VisitorBasedCodemodCommand.__class__]] = [
    ("guard_none", GuardNoneTransformer),
    ("import_fix", ImportFixTransformer),
]
