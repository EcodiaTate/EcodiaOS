# scripts/route_audit.py
from __future__ import annotations

import inspect
import os

from fastapi.routing import APIRoute
from pydantic import BaseModel

FASTAPI_NON_BODY = {
    "Request",
    "Response",
    "Depends",
    "Query",
    "Path",
    "Header",
    "Body",
    "File",
    "UploadFile",
    "BackgroundTasks",
    "WebSocket",
    "Form",
}


def audit_route_bodies(app) -> None:
    """Log any POST/PUT/PATCH body params that are NOT Pydantic models."""
    problems = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        if not (set(r.methods) & {"POST", "PUT", "PATCH"}):
            continue

        sig = inspect.signature(r.endpoint)
        for name, param in sig.parameters.items():
            if name in {"self", "request", "response"}:
                continue
            ann = param.annotation
            if ann is inspect._empty:
                continue

            # resolve forward refs if possible
            if isinstance(ann, str):
                try:
                    ann = eval(ann, r.endpoint.__globals__)  # dev-only
                except Exception:
                    pass

            # skip obvious FastAPI types
            typ_name = getattr(ann, "__name__", None) or str(ann)
            if any(k in typ_name for k in FASTAPI_NON_BODY):
                continue

            # if it's a class, ensure it subclasses BaseModel
            if isinstance(ann, type):
                if not issubclass(ann, BaseModel):
                    problems.append(
                        (
                            sorted(r.methods),
                            r.path,
                            r.endpoint.__name__,
                            typ_name,
                            "NOT a BaseModel",
                        ),
                    )
                break
            else:
                # unions/typing – if none of the args is a BaseModel, flag
                if "BaseModel" not in typ_name and "pydantic" not in typ_name:
                    problems.append(
                        (
                            sorted(r.methods),
                            r.path,
                            r.endpoint.__name__,
                            typ_name,
                            "Annotation not a class",
                        ),
                    )
                break

    if problems:
        print("\n[ROUTE-AUDIT] Offending route bodies:", flush=True)
        for methods, path, fn, typ, why in problems:
            print(f"  {methods} {path} :: {fn} -> {typ} ({why})", flush=True)
        # HARD FAIL only if env flag set
        if os.getenv("AUDIT_HARD_FAIL", "0") not in ("", "0", "false", "False"):
            raise RuntimeError("Route body audit failed — see [ROUTE-AUDIT] above.")
    else:
        print("[ROUTE-AUDIT] OK: all POST/PUT/PATCH bodies are valid Pydantic models.", flush=True)
