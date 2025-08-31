from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

wm_symbols_router = APIRouter()


class SymbolsResponse(BaseModel):
    path: str
    symbols: list[dict[str, Any]]


def _extract_symbols_py(src: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        tree = ast.parse(src)
    except Exception:
        return out

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            out.append({"kind": "func", "name": node.name, "lineno": getattr(node, "lineno", 1)})
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            out.append({"kind": "func", "name": node.name, "lineno": getattr(node, "lineno", 1)})
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef):
            out.append({"kind": "class", "name": node.name, "lineno": getattr(node, "lineno", 1)})
            self.generic_visit(node)

    V().visit(tree)
    return out


@wm_symbols_router.get("/", response_model=SymbolsResponse)
async def symbols(path: str = Query(..., description="Repo-relative file path")) -> SymbolsResponse:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"read failed: {e!r}")
    syms = _extract_symbols_py(text) if p.suffix == ".py" else []
    return SymbolsResponse(path=path, symbols=syms)
