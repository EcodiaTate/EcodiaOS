#!/usr/bin/env python3
# eos_schema_scan.py
# Collate function signatures, returns, classes, and FastAPI endpoints across a codebase.
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}
DEFAULT_IGNORES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "venv",
    ".venv",
    "env",
    ".env",
    ".tox",
}
DEFAULT_EXT = {".py"}


# ------------- Helpers -------------
def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def expr_to_str(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)  # py>=3.9
    except Exception:
        # crude fallback
        if isinstance(node, ast.Attribute):
            return f"{expr_to_str(node.value)}.{node.attr}"
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return repr(node.value)
        return node.__class__.__name__


def const_value(node: ast.AST | None) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "NA"


def is_pydantic_base(bases: list[ast.expr]) -> bool:
    # detect BaseModel or pydantic.BaseModel
    for b in bases:
        s = expr_to_str(b) or ""
        if s.endswith("BaseModel") or s.endswith("pydantic.BaseModel"):
            return True
    return False


def is_dataclass(decorators: list[ast.expr]) -> bool:
    for d in decorators:
        s = expr_to_str(d) or ""
        if s.startswith("dataclass") or ".dataclass" in s:
            return True
    return False


def collect_class_fields(body: list[ast.stmt]) -> list[dict[str, Any]]:
    # Capture simple annotated assignments at class level
    out = []
    for n in body:
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.append(
                {
                    "name": n.target.id,
                    "type": expr_to_str(n.annotation),
                    "default": expr_to_str(n.value) if n.value is not None else None,
                },
            )
    return out


def arg_to_dict(
    arg: ast.arg,
    default: ast.expr | None,
    annotation: ast.expr | None,
) -> dict[str, Any]:
    return {
        "name": arg.arg,
        "annotation": expr_to_str(annotation),
        "default": expr_to_str(default) if default is not None else None,
    }


def signature_of(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    a = func.args
    pos_defaults = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults)
    params: list[dict[str, Any]] = []
    for arg, dflt in zip(a.args, pos_defaults):
        params.append(arg_to_dict(arg, dflt, arg.annotation))
    if a.vararg:
        params.append(
            {
                "name": "*" + a.vararg.arg,
                "annotation": expr_to_str(a.vararg.annotation),
                "default": None,
            },
        )
    for arg, dflt in zip(a.kwonlyargs, a.kw_defaults):
        params.append(arg_to_dict(arg, dflt, arg.annotation))
    if a.kwarg:
        params.append(
            {
                "name": "**" + a.kwarg.arg,
                "annotation": expr_to_str(a.kwarg.annotation),
                "default": None,
            },
        )
    return {
        "name": func.name,
        "parameters": params,
        "return": expr_to_str(func.returns),
    }


def decorator_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    out = []
    for d in func.decorator_list:
        s = expr_to_str(d)
        if s:
            out.append(s)
    return out


def parse_endpoint_decorator(dec: ast.expr) -> dict[str, Any] | None:
    """
    Recognize @router.get("/path", response_model=Model, status_code=200, tags=[...])
    or @app.post(...), @something.patch(...). Returns a dict or None.
    """
    if not isinstance(dec, ast.Call):  # must be a call (i.e., decorator with args)
        return None
    fn = dec.func
    if not isinstance(fn, ast.Attribute):
        return None
    method = fn.attr.lower()
    if method not in HTTP_METHODS:
        return None

    # Best-effort extract path (first positional string or kw 'path')
    path = None
    if dec.args:
        path = const_value(dec.args[0])
    if path is None:
        for kw in dec.keywords or []:
            if kw.arg == "path":
                path = const_value(kw.value)
                break

    # response_model, status_code, tags
    response_model = None
    status_code = None
    tags = None
    for kw in dec.keywords or []:
        if kw.arg == "response_model":
            response_model = expr_to_str(kw.value)
        elif kw.arg == "status_code":
            status_code = const_value(kw.value)
        elif kw.arg == "tags":
            # could be a list literal
            if isinstance(kw.value, ast.List):
                tags = [
                    const_value(elt) if isinstance(elt, ast.Constant) else expr_to_str(elt)
                    for elt in kw.value.elts
                ]
            else:
                tags = expr_to_str(kw.value)

    router_var = expr_to_str(fn.value)  # e.g., "router" or "app" or "main_router"
    return {
        "method": method.upper(),
        "path": path or "(dynamic)",
        "router_var": router_var,
        "response_model": response_model,
        "status_code": status_code,
        "tags": tags,
    }


# ------------- Data carriers -------------
@dataclass
class FunctionInfo:
    name: str
    signature: dict[str, Any]
    decorators: list[str]
    docstring: str | None


@dataclass
class ClassInfo:
    name: str
    bases: list[str]
    decorators: list[str]
    docstring: str | None
    methods: list[FunctionInfo] = field(default_factory=list)
    is_pydantic_model: bool = False
    is_dataclass: bool = False
    fields: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ModuleInfo:
    path: str
    file_hash: str
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    endpoints: list[dict[str, Any]] = field(default_factory=list)


# ------------- Core scanner -------------
class PyModuleScanner(ast.NodeVisitor):
    def __init__(self, module_path: str):
        self.module_path = module_path
        self.functions: list[FunctionInfo] = []
        self.classes: list[ClassInfo] = []
        self.endpoints: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        sig = signature_of(node)
        decs = decorator_names(node)
        # scan for endpoint decorators
        for d in node.decorator_list:
            ep = parse_endpoint_decorator(d)
            if ep:
                ep["handler"] = node.name
                ep["module"] = self.module_path
                self.endpoints.append(ep)
        info = FunctionInfo(
            name=node.name,
            signature=sig,
            decorators=decs,
            docstring=ast.get_docstring(node),
        )
        self.functions.append(info)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        # treat same as FunctionDef
        sig = signature_of(node)
        decs = decorator_names(node)
        for d in node.decorator_list:
            ep = parse_endpoint_decorator(d)
            if ep:
                ep["handler"] = node.name
                ep["module"] = self.module_path
                self.endpoints.append(ep)
        info = FunctionInfo(
            name=node.name,
            signature=sig,
            decorators=decs,
            docstring=ast.get_docstring(node),
        )
        self.functions.append(info)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        bases = [expr_to_str(b) for b in node.bases] if node.bases else []
        decs = [expr_to_str(d) for d in node.decorator_list] if node.decorator_list else []
        methods: list[FunctionInfo] = []
        for n in node.body:
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                methods.append(
                    FunctionInfo(
                        name=n.name,
                        signature=signature_of(n),
                        decorators=decorator_names(n),
                        docstring=ast.get_docstring(n),
                    ),
                )
        cls = ClassInfo(
            name=node.name,
            bases=bases,
            decorators=[d for d in decs if d],
            docstring=ast.get_docstring(node),
            methods=methods,
            is_pydantic_model=is_pydantic_base(node.bases),
            is_dataclass=is_dataclass(node.decorator_list),
            fields=collect_class_fields(node.body),
        )
        self.classes.append(cls)
        self.generic_visit(node)


def scan_python_file(path: str) -> ModuleInfo | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        return None
    scanner = PyModuleScanner(module_path=path)
    scanner.visit(tree)
    return ModuleInfo(
        path=path,
        file_hash=hash_file(path),
        functions=scanner.functions,
        classes=scanner.classes,
        endpoints=scanner.endpoints,
    )


def walk_files(
    root: str,
    include_ext: set[str] = DEFAULT_EXT,
    ignores: set[str] = DEFAULT_IGNORES,
) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune ignored directories
        dirnames[:] = [d for d in dirnames if d not in ignores]
        for fn in filenames:
            _, ext = os.path.splitext(fn)
            if ext.lower() in include_ext:
                out.append(os.path.join(dirpath, fn))
    return out


# ------------- Formatting -------------
def build_json_report(root: str, modules: list[ModuleInfo]) -> dict[str, Any]:
    endpoints: list[dict[str, Any]] = []
    func_count = 0
    class_count = 0
    model_count = 0
    for m in modules:
        endpoints.extend(m.endpoints)
        func_count += len(m.functions)
        class_count += len(m.classes)
        model_count += sum(1 for c in m.classes if c.is_pydantic_model)
    return {
        "scanned_at": now_iso(),
        "root": root,
        "counts": {
            "modules": len(modules),
            "functions": func_count,
            "classes": class_count,
            "pydantic_models": model_count,
            "endpoints": len(endpoints),
        },
        "endpoints": endpoints,
        "modules": [
            {
                "path": m.path,
                "file_hash": m.file_hash,
                "functions": [
                    {
                        "name": f.name,
                        "signature": f.signature,
                        "decorators": f.decorators,
                        "docstring": f.docstring,
                    }
                    for f in m.functions
                ],
                "classes": [
                    {
                        "name": c.name,
                        "bases": c.bases,
                        "decorators": c.decorators,
                        "docstring": c.docstring,
                        "is_pydantic_model": c.is_pydantic_model,
                        "is_dataclass": c.is_dataclass,
                        "fields": c.fields,
                        "methods": [
                            {
                                "name": mm.name,
                                "signature": mm.signature,
                                "decorators": mm.decorators,
                                "docstring": mm.docstring,
                            }
                            for mm in c.methods
                        ],
                    }
                    for c in m.classes
                ],
            }
            for m in modules
        ],
    }


def md_escape(s: str) -> str:
    return s.replace("|", r"\|") if isinstance(s, str) else s


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# EcodiaOS Schema Overview")
    lines.append("")
    counts = report.get("counts", {})
    lines.append(f"- **Scanned at:** {report.get('scanned_at')}")
    lines.append(f"- **Root:** `{report.get('root')}`")
    lines.append(
        f"- **Modules:** {counts.get('modules', 0)}  —  "
        f"**Functions:** {counts.get('functions', 0)}  —  "
        f"**Classes:** {counts.get('classes', 0)}  —  "
        f"**FastAPI Endpoints:** {counts.get('endpoints', 0)}",
    )
    lines.append("")

    # Endpoints table
    eps = report.get("endpoints", [])
    if eps:
        lines.append("## FastAPI Endpoints")
        lines.append("")
        lines.append("| Method | Path | Handler | Module | Response Model | Status | Tags |")
        lines.append("|---|---|---|---|---|---:|---|")
        for e in sorted(eps, key=lambda x: (x.get("path") or "", x.get("method") or "")):
            tags = e.get("tags")
            if isinstance(tags, list):
                tags_str = ", ".join(str(t) for t in tags)
            else:
                tags_str = str(tags) if tags is not None else ""
            lines.append(
                f"| {e.get('method')} | `{md_escape(e.get('path') or '')}` | "
                f"`{e.get('handler')}` | `{e.get('module')}` | "
                f"`{md_escape(str(e.get('response_model') or ''))}` | "
                f"{str(e.get('status_code') or '')} | {md_escape(tags_str)} |",
            )
        lines.append("")

    # Per module summary
    lines.append("## Modules")
    lines.append("")
    for m in report.get("modules", []):
        rel = m.get("path")
        lines.append(f"### `{rel}`")

        # Classes
        classes = m.get("classes", [])
        if classes:
            lines.append("**Classes**")
            for c in classes:
                badges = []
                if c.get("is_pydantic_model"):
                    badges.append("pydantic")
                if c.get("is_dataclass"):
                    badges.append("dataclass")
                badge_str = f" _({' / '.join(badges)})_" if badges else ""
                bases = ", ".join(c.get("bases") or [])
                lines.append(f"- **{c['name']}**{badge_str}  bases: `{bases}`")

                # Methods (brief)
                ms = c.get("methods") or []
                for mm in ms:
                    sig = mm.get("signature", {})
                    params = ", ".join(
                        p.get("name", "")
                        + (f": {p.get('annotation')}" if p.get("annotation") else "")
                        + (f" = {p.get('default')}" if p.get("default") else "")
                        for p in sig.get("parameters", [])
                    )
                    ret = f" -> {sig.get('return')}" if sig.get("return") else ""
                    lines.append(f"  - `{mm['name']}({md_escape(params)}){ret}`")

        # Functions
        funcs = m.get("functions", [])
        if funcs:
            lines.append("**Functions**")
            for f in funcs:
                sig = f.get("signature", {})
                params = ", ".join(
                    p.get("name", "")
                    + (f": {p.get('annotation')}" if p.get("annotation") else "")
                    + (f" = {p.get('default')}" if p.get("default") else "")
                    for p in sig.get("parameters", [])
                )
                ret = f" -> {sig.get('return')}" if sig.get("return") else ""
                lines.append(f"- `{f['name']}({md_escape(params)}){ret}`")

        lines.append("")
    return "\n".join(lines)


# ------------- Watch (no external deps) -------------
def build_state(files: list[str]) -> dict[str, float]:
    return {p: os.path.getmtime(p) for p in files if os.path.exists(p)}


def diff_state(old: dict[str, float], root: str) -> tuple[bool, dict[str, float], list[str]]:
    files = walk_files(root)
    changed = False
    new_state: dict[str, float] = {}
    changed_files: list[str] = []
    for p in files:
        try:
            m = os.path.getmtime(p)
        except Exception:
            continue
        new_state[p] = m
        if p not in old or old[p] != m:
            changed = True
            changed_files.append(p)
    # detect deletions
    for p in old:
        if p not in new_state:
            changed = True
    return changed, new_state, changed_files


# ------------- CLI -------------
def run_scan(root: str, out_dir: str, fmt: str) -> dict[str, Any]:
    files = walk_files(root)
    mods: list[ModuleInfo] = []
    for p in files:
        if p.lower().endswith(".py"):
            mi = scan_python_file(p)
            if mi:
                mods.append(mi)
    report = build_json_report(root, mods)
    os.makedirs(out_dir, exist_ok=True)
    wrote = []
    if fmt in ("json", "both"):
        json_path = os.path.join(out_dir, "schema_overview.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        wrote.append(json_path)
    if fmt in ("md", "both"):
        md_path = os.path.join(out_dir, "schema_overview.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(build_markdown(report))
        wrote.append(md_path)
    print(f"[SCAN] {len(mods)} modules → wrote: {', '.join(wrote)}")
    return report


def main():
    ap = argparse.ArgumentParser(
        description="EcodiaOS schema scanner (functions, classes, endpoints).",
    )
    ap.add_argument(
        "--root",
        default=os.getenv("ECO_ROOT", "."),
        help="Codebase root (e.g., D:\\EcodiaOS).",
    )
    ap.add_argument("--out", default="./schema_overview", help="Output directory for JSON/MD.")
    ap.add_argument(
        "--format",
        choices=["json", "md", "both"],
        default="both",
        help="Output format.",
    )
    ap.add_argument("--watch", action="store_true", help="Re-scan on changes (simple polling).")
    ap.add_argument("--interval", type=float, default=3.0, help="Watch polling interval (seconds).")
    ap.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        help="Extra directories to ignore (space-separated).",
    )
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    DEFAULT_IGNORES.union(set(args.ignore))
    # First run
    run_scan(root, args.out, args.format)

    if not args.watch:
        return 0

    state = build_state(walk_files(root))
    print(f"[WATCH] Watching {root} (interval={args.interval}s). Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(args.interval)
            changed, state, changed_files = diff_state(state, root)
            if changed:
                print(f"[WATCH] Detected changes in {len(changed_files)} file(s). Re-scanning...")
                run_scan(root, args.out, args.format)
    except KeyboardInterrupt:
        print("\n[WATCH] Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
