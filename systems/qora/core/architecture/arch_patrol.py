# systems/qora/patrol/arch_patrol.py
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

from core.utils.neo.cypher_query import cypher_query

ROOTS = [Path("core"), Path("systems"), Path("api")]


def _blake(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=16).hexdigest()


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _parse_tools_from_file(p: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    src = _read(p)
    if not src:
        return out
    try:
        tree = ast.parse(src, filename=str(p))
    except SyntaxError:
        return out

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            decos = [ast.get_source_segment(src, d) or "" for d in (node.decorator_list or [])]
            tool_meta = _extract_tool_meta(decos)
            qual = node.name
            mod = _infer_module(p)
            uid = _blake(f"{mod}:{qual}")
            doc = ast.get_docstring(node) or ""
            record = {
                "uid": uid,
                "module": mod,
                "qualname": qual,
                "docstring": doc,
                "decorators": decos,
                "tool_name": tool_meta.get("name"),
                "tool_desc": tool_meta.get("description"),
                "tool_params_schema": tool_meta.get("inputs") or {},
                "tool_outputs_schema": tool_meta.get("outputs") or {},
                "tool_agent": tool_meta.get("agent") or "*",
                "tool_caps": tool_meta.get("capabilities") or [],
                "safety_tier": int(tool_meta.get("safety_tier", 3)),
                "allow_external": bool(tool_meta.get("allow_external", False)),
            }
            out.append(record)
            self.generic_visit(node)

    V().visit(tree)
    return out


def _extract_tool_meta(decos_src: list[str]) -> dict[str, Any]:
    for d in decos_src:
        if "eos_tool(" not in d:
            continue
        try:
            node = ast.parse(d.strip()).body[0].value  # type: ignore
            if not isinstance(node, ast.Call):
                continue
            kwargs = {}
            for kw in node.keywords or []:
                try:
                    kwargs[kw.arg] = ast.literal_eval(kw.value)
                except Exception:
                    kwargs[kw.arg] = None
            return kwargs
        except Exception:
            continue
    return {}


def _infer_module(p: Path) -> str:
    # rough: convert path to dotted module from repo root
    rp = p.with_suffix("")
    parts = list(rp.parts)
    # find first package root by presence of 'systems'/'core'/'api'
    for i, part in enumerate(parts):
        if part in ("core", "systems", "api"):
            return ".".join(parts[i:])
    return ".".join(parts)


async def patrol_once() -> int:
    batch: list[dict[str, Any]] = []
    for root in ROOTS:
        for p in root.rglob("*.py"):
            batch.extend(_parse_tools_from_file(p))
    if not batch:
        return 0
    await _upsert_functions_batch(batch)
    return len(batch)


async def _upsert_functions_batch(rows: list[dict[str, Any]]) -> None:
    cy = """
    UNWIND $rows AS row
    MERGE (fn:SystemFunction { uid: row.uid })
    SET fn.module = row.module,
        fn.qualname = row.qualname,
        fn.docstring = row.docstring,
        fn.decorators = row.decorators,
        fn.tool_name = row.tool_name,
        fn.tool_desc = row.tool_desc,
        fn.tool_params_schema = row.tool_params_schema,
        fn.tool_outputs_schema = row.tool_outputs_schema,
        fn.tool_agent = row.tool_agent,
        fn.tool_caps = row.tool_caps,
        fn.safety_tier = row.safety_tier,
        fn.allow_external = row.allow_external,
        fn.updated_at = timestamp()
    """
    await cypher_query(cy, {"rows": rows})
