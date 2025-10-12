# systems/simula/code_sim/mutators/ast_refactor.py
"""
AST-driven refactoring & scaffolding for Simula

Purpose
-------
Produce deterministic, structure-correct unified diffs that:
- Scaffold missing modules/functions/classes from step targets
- Repair imports (add/normalize) based on usage and constraints
- Tighten typing (add annotations, Optional, return types)
- Harden error paths (explicit exceptions, guard clauses, logging)
- Perform small, safe rewrites that unblock tests/static analysis

Key Principles
--------------
- No side effects: returns *diff text only*. Orchestrator applies/rolls back.
- Idempotent: running the same mutation twice yields the same file content.
- Conservative by default; "aggressive" toggled by Portfolio when needed.
- Stdlib-only. Python ≥3.11 assumed by Simula constraints.

Public API
----------
AstMutator.mutate(step, mode) -> Optional[str]
  modes: "scaffold", "imports", "typing", "error_paths"

Implementation Notes
--------------------
- Uses Python's `ast` for correctness; relies on `ast.unparse` for codegen.
- Preserves module headers and critical comments via a simple preamble keeper.
- Generates *unified diff* with standard a/<rel> and b/<rel> paths.

Limitations
-----------
- Does not attempt deep semantic edits; this is a structural un-blocker.
- Typing mode heuristics are intentionally conservative to avoid churn.
"""

from __future__ import annotations

import ast
import difflib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Repo root (stringly path for safety inside containers/CI)
REPO_ROOT = Path(os.environ.get("SIMULA_REPO_ROOT", Path.cwd())).resolve()


# =========================
# Small utilities
# =========================


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _rel_for_diff(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
    except Exception:
        rel = path.name  # fallback
    return rel


def _unified_diff(old: str, new: str, rel_path: str) -> str:
    a = old.splitlines(True)
    b = new.splitlines(True)
    return "".join(
        difflib.unified_diff(a, b, fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", lineterm=""),
    )


def _strip_shebang_and_encoding(src: str) -> tuple[str, str]:
    """Return (preamble, body) where preamble keeps shebang/encoding/comment banner."""
    lines = src.splitlines(True)
    pre: list[str] = []
    i = 0
    for i, ln in enumerate(lines):
        if i == 0 and ln.startswith("#!"):
            pre.append(ln)
            continue
        if re.match(r"#\s*-\*-\s*coding:", ln):
            pre.append(ln)
            continue
        if ln.startswith("#") and i < 8:
            pre.append(ln)
            continue
        if ln.strip() == "" and i < 6:
            pre.append(ln)
            continue
        break
    else:
        i += 1
    body = "".join(lines[i:])
    return ("".join(pre), body)


def _ensure_module_docstring(tree: ast.Module, doc: str) -> None:
    if not (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(getattr(tree.body[0], "value", None), ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        tree.body.insert(0, ast.Expr(value=ast.Constant(value=doc)))


def _parse_sig(signature: str) -> tuple[str, list[str]]:
    """Parse 'name(arg: T, x: int) -> R' into (name, [param names])."""
    head = signature.strip()
    name = head.split("(", 1)[0].strip()
    inside = head.split("(", 1)[1].rsplit(")", 1)[0] if "(" in head and ")" in head else ""
    params = [p.split(":")[0].split("=")[0].strip() for p in inside.split(",") if p.strip()]
    return name, params


def _build_func_def_from_sig(signature: str, doc: str) -> ast.FunctionDef:
    """
    Best-effort: synthesis a FunctionDef with typed args from a human signature.
    - NO NotImplementedError: we generate a non-throwing stub (docstring + pass)
    - Types are parsed literally; unknowns become `Any` (typing import added elsewhere)
    """
    name = signature.strip().split("(", 1)[0].strip()
    ret_ann = None
    if "->" in signature:
        ret_part = signature.split("->", 1)[1].strip()
        if ret_part:
            base = ret_part.replace("[", " ").replace("]", " ").split()[0]
            if base:
                ret_ann = ast.Name(id=base, ctx=ast.Load())

    args_blob = signature.split("(", 1)[1].rsplit(")", 1)[0] if "(" in signature else ""
    args = ast.arguments(
        posonlyargs=[],
        args=[],
        kwonlyargs=[],
        kw_defaults=[],
        defaults=[],
        vararg=None,
        kwarg=None,
    )
    for p in [s.strip() for s in args_blob.split(",") if s.strip()]:
        nm = p.split(":")[0].split("=")[0].strip()
        ann = None
        if ":" in p:
            typ = p.split(":", 1)[1].strip().split("=")[0].strip()
            base = typ.replace("[", " ").replace("]", " ").split()[0]
            if base:
                ann = ast.Name(id=base, ctx=ast.Load())
        args.args.append(ast.arg(arg=nm, annotation=ann))

    body = [
        ast.Expr(value=ast.Constant(value=doc)),  # docstring must be first
        ast.Pass(),
    ]
    fn = ast.FunctionDef(
        name=name,
        args=args,
        body=body,
        decorator_list=[],
        returns=ret_ann,
        type_comment=None,
    )
    ast.fix_missing_locations(fn)
    return fn


def _ensure_import(
    module: ast.Module,
    name: str,
    asname: str | None = None,
    from_: str | None = None,
) -> bool:
    """Ensure an import is present; return True if modified."""

    def has_import() -> bool:
        for node in module.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == name and (asname is None or alias.asname == asname):
                        return True
            if isinstance(node, ast.ImportFrom) and node.module == from_:
                for alias in node.names:
                    if alias.name == name and (asname is None or alias.asname == asname):
                        return True
        return False

    if has_import():
        return False

    imp = (
        ast.ImportFrom(module=from_, names=[ast.alias(name=name, asname=asname)], level=0)
        if from_
        else ast.Import(names=[ast.alias(name=name, asname=asname)])
    )
    # Insert after module docstring if present
    insert_at = (
        1
        if (
            module.body
            and isinstance(module.body[0], ast.Expr)
            and isinstance(getattr(module.body[0], "value", None), ast.Constant)
        )
        else 0
    )
    module.body.insert(insert_at, imp)
    ast.fix_missing_locations(module)
    return True


def _ensure_logger(module: ast.Module) -> None:
    modified = False
    modified |= _ensure_import(module, "logging")
    # ensure logger variable if missing
    for node in module.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "logger":
                    return
    assign = ast.Assign(
        targets=[ast.Name(id="logger", ctx=ast.Store())],
        value=ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="logging", ctx=ast.Load()),
                attr="getLogger",
                ctx=ast.Load(),
            ),
            args=[ast.Name(id="__name__", ctx=ast.Load())],
            keywords=[],
        ),
        type_comment=None,
    )
    # place after imports/docstring cluster
    idx = 0
    for i, n in enumerate(module.body[:6]):
        if isinstance(n, ast.Import | ast.ImportFrom) or (
            isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant)
        ):
            idx = i + 1
    module.body.insert(idx, assign)
    ast.fix_missing_locations(module)


def _module_has_function(module: ast.Module, name: str) -> bool:
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in module.body)


def _add_guard_raises(fn: ast.FunctionDef, exc: str = "ValueError") -> bool:
    """
    Insert a minimal guard on the first argument if no guard present.
    """
    if not fn.args.args:
        return False
    if any(isinstance(n, ast.Raise) for n in fn.body[:2]):
        return False
    # skip if a top guard already exists
    for n in fn.body[:3]:
        if isinstance(n, ast.If):
            return False
    first = fn.args.args[0]
    cond = ast.UnaryOp(op=ast.Not(), operand=ast.Name(id=first.arg, ctx=ast.Load()))
    msg = ast.Constant(value=f"Invalid '{first.arg}'")
    raise_stmt = ast.Raise(
        exc=ast.Call(func=ast.Name(id=exc, ctx=ast.Load()), args=[msg], keywords=[]),
        cause=None,
    )
    fn.body.insert(0, ast.If(test=cond, body=[raise_stmt], orelse=[]))
    ast.fix_missing_locations(fn)
    return True


def _ensure_return_annotations(fn: ast.FunctionDef) -> bool:
    if fn.returns is not None:
        return False
    # Simple heuristic:
    # - is_/has_/can_/should_ -> bool
    # - get/find/load/fetch   -> Optional[Any]
    # - otherwise             -> Any
    name = fn.name.lower()
    if name.startswith(("is_", "has_", "can_", "should_", "valid")):
        fn.returns = ast.Name(id="bool", ctx=ast.Load())
    elif name.startswith(("get", "find", "load", "fetch")):
        fn.returns = ast.Subscript(
            value=ast.Name(id="Optional", ctx=ast.Load()),
            slice=ast.Name(id="Any", ctx=ast.Load()),
            ctx=ast.Load(),
        )
    else:
        fn.returns = ast.Name(id="Any", ctx=ast.Load())
    ast.fix_missing_locations(fn)
    return True


def _ensure_arg_annotations(fn: ast.FunctionDef) -> bool:
    modified = False
    for a in fn.args.args:
        if a.annotation is None:
            a.annotation = ast.Name(id="Any", ctx=ast.Load())
            modified = True
    if modified:
        ast.fix_missing_locations(fn)
    return modified


# =========================
# Mutator
# =========================


@dataclass
class AstMutator:
    aggressive: bool = False

    def set_aggressive(self, v: bool) -> None:
        self.aggressive = bool(v)

    # ---- Public entrypoint ----

    def mutate(self, step_dict: dict[str, Any], mode: str = "scaffold") -> str | None:
        """
        Return a unified diff for the primary target file, or None if no-op.
        Modes:
          - scaffold: ensure module + target function exists with docstring & logger
          - imports: add missing imports for typing/logging/typing.Optional
          - typing: add Any/Optional/return annotations conservatively
          - error_paths: insert minimal guard raises & error logs
        """
        targets = step_dict.get("targets", [])
        primary_target = targets[0] if targets and isinstance(targets, list) else {}
        target_file = primary_target.get("file")
        export_sig = primary_target.get("export")

        if not target_file:
            return None
        path = (REPO_ROOT / target_file).resolve()
        old_src = _read(path)
        preamble, body = _strip_shebang_and_encoding(old_src)
        if not body.strip():
            body = "\n"  # keep parseable when empty

        try:
            tree = ast.parse(body)
        except SyntaxError:
            tree = ast.parse("")  # start clean if broken

        changed = False

        if mode == "scaffold":
            step_name = step_dict.get("name", "simula")
            changed |= self._do_scaffold(
                tree,
                export_sig,
                step_name=step_name,
            )
            _ensure_logger(tree)  # always ensure logger on scaffold
        elif mode == "imports":
            changed |= self._do_imports(tree)
        elif mode == "typing":
            changed |= self._do_typing(tree)
        elif mode == "error_paths":
            changed |= self._do_error_paths(tree)
        else:
            return None

        if not changed:
            return None

        # Build new source (idempotent, preserve preamble)
        new_body = ast.unparse(tree)
        new_src = preamble + new_body + ("" if new_body.endswith("\n") else "\n")

        rel = _rel_for_diff(path)
        return _unified_diff(old_src, new_src, rel)

    # ---- Mode handlers ----

    def _do_scaffold(self, module: ast.Module, export_sig: str | None, step_name: str) -> bool:
        modified = False
        _ensure_module_docstring(module, f"Autogenerated by Simula step: {step_name}")
        if export_sig:
            fn_name, _ = _parse_sig(export_sig)
            if not _module_has_function(module, fn_name):
                module.body.append(
                    _build_func_def_from_sig(export_sig, f"{step_name}: autogenerated stub"),
                )
                modified = True
            # ensure logger usage inside function (info on entry) after docstring
            for node in module.body:
                if isinstance(node, ast.FunctionDef) and node.name == fn_name:
                    # compute insert index: after docstring if present
                    insert_at = (
                        1
                        if (
                            node.body
                            and isinstance(node.body[0], ast.Expr)
                            and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                        )
                        else 0
                    )
                    has_info = any(
                        isinstance(n, ast.Expr)
                        and isinstance(getattr(n, "value", None), ast.Call)
                        and isinstance(getattr(n.value, "func", None), ast.Attribute)
                        and getattr(n.value.func, "attr", "") == "info"
                        for n in node.body[:2]
                    )
                    if not has_info:
                        call = ast.Expr(
                            value=ast.Call(
                                func=ast.Attribute(
                                    value=ast.Name(id="logger", ctx=ast.Load()),
                                    attr="info",
                                    ctx=ast.Load(),
                                ),
                                args=[ast.Constant(value=f"{fn_name}() called")],
                                keywords=[],
                            ),
                        )
                        node.body.insert(insert_at, call)
                        ast.fix_missing_locations(node)
                        modified = True
        return modified

    def _do_imports(self, module: ast.Module) -> bool:
        modified = False
        modified |= _ensure_import(module, "logging")
        # typing essentials if used elsewhere
        modified |= _ensure_import(module, "Any", from_="typing")
        modified |= _ensure_import(module, "Optional", from_="typing")
        _ensure_logger(module)
        return modified

    def _do_typing(self, module: ast.Module) -> bool:
        modified = False
        any_arg_or_ret = False
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                any_arg_or_ret |= _ensure_arg_annotations(node)
                any_arg_or_ret |= _ensure_return_annotations(node)
        if any_arg_or_ret:
            modified |= _ensure_import(module, "Any", from_="typing")
            modified |= _ensure_import(module, "Optional", from_="typing")
        return modified or any_arg_or_ret

    def _do_error_paths(self, module: ast.Module) -> bool:
        modified = False
        _ensure_logger(module)
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                modified |= _add_guard_raises(node, exc="ValueError")
                # if a Raise exists, prepend a logger.error for traceability
                for i, stmt in enumerate(list(node.body)):
                    if isinstance(stmt, ast.Raise):
                        prev = node.body[i - 1] if i > 0 else None
                        already_logged = (
                            isinstance(prev, ast.Expr)
                            and isinstance(getattr(prev, "value", None), ast.Call)
                            and isinstance(getattr(prev.value, "func", None), ast.Attribute)
                            and getattr(prev.value.func, "attr", "") in {"error", "exception"}
                        )
                        if not already_logged:
                            err = ast.Expr(
                                value=ast.Call(
                                    func=ast.Attribute(
                                        value=ast.Name(id="logger", ctx=ast.Load()),
                                        attr="error",
                                        ctx=ast.Load(),
                                    ),
                                    args=[ast.Constant(value=f"{node.name} raised")],
                                    keywords=[],
                                ),
                            )
                            node.body.insert(i, err)
                            ast.fix_missing_locations(node)
                            modified = True
                        break
        return modified
