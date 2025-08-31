from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import time

from systems.qora.manifest.registry_client import get_endpoint_aliases

from .models import ContentRef, SystemManifest

ENDPOINTS_RE = re.compile(r"ENDPOINTS\.(?P<alias>[A-Z0-9_]+)")
HEADER_RE = re.compile(r'["\']x-decision-id["\']|["\']x-budget-ms["\']', re.I)
EVENT_PUB_RE = re.compile(r"\bpublish\(['\"](?P<topic>[^'\"]+)['\"]", re.I)
TOOL_DECORATOR_NAMES = {"eos_tool", "tool", r"eos\.tool"}  # tolerant


def _iter_py(root: str):
    for b, _, fs in os.walk(root):
        for fn in fs:
            if fn.endswith(".py") and not fn.startswith("."):
                yield os.path.join(b, fn).replace("\\", "/")


def _blake(data: bytes, n=16):
    return hashlib.blake2b(data, digest_size=n).hexdigest()


def _slice_ref(path: str, lo=1, hi=120) -> ContentRef:
    try:
        lines = open(path, "rb").read().splitlines()
        blob = b"\n".join(lines[max(0, lo - 1) : min(len(lines), hi)])
        return ContentRef(file=path, start=lo, end=hi, hash=_blake(blob))
    except Exception:
        return ContentRef(file=path, start=0, end=0, hash="0" * 32)


def _scan_imports(path: str, tree: ast.AST | None) -> list[tuple[str, str]]:
    if not tree:
        return []
    out: list[tuple[str, str]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.append((path, a.name))
        elif isinstance(n, ast.ImportFrom):
            out.append((path, n.module or ""))
    return out


def _scan_endpoints(path: str, text: str, aliases: dict[str, str]) -> list[dict]:
    rows = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in ENDPOINTS_RE.finditer(line):
            alias = m.group("alias").upper()
            rows.append({"alias": alias, "path": aliases.get(alias), "file": path, "line": i})
    return rows


def _scan_tools_and_models(path: str, tree: ast.AST | None) -> tuple[list[dict], list[dict]]:
    tools, models = [], []
    if not tree:
        return tools, models
    for n in ast.walk(tree):
        # Tools: detect decorators named eos_tool/tool
        if isinstance(n, ast.FunctionDef) or isinstance(n, ast.AsyncFunctionDef):
            for d in n.decorator_list or []:
                name = getattr(d, "id", None) or getattr(d, "attr", None) or ""
                if (
                    name in TOOL_DECORATOR_NAMES
                    or str(getattr(getattr(d, "func", None), "attr", "")) in TOOL_DECORATOR_NAMES
                ):
                    req_args = [a.arg for a in (n.args.args or [])][
                        : max(0, len(n.args.args) - (len(n.args.defaults or [])))
                    ]
                    tools.append(
                        {
                            "uid": f"{path}:{n.name}",
                            "name": n.name,
                            "file": path,
                            "line": n.lineno,
                            "required_args": req_args,
                        },
                    )
        # Pydantic models (heuristic)
        if isinstance(n, ast.ClassDef):
            if any(
                getattr(b, "id", "") == "BaseModel"
                or getattr(getattr(b, "attr", None), "id", "") == "BaseModel"
                for b in n.bases
            ):
                fields = []
                for body in n.body:
                    if isinstance(body, ast.AnnAssign) and hasattr(body, "target"):
                        fname = getattr(body.target, "id", None) or getattr(
                            getattr(body.target, "attr", None),
                            "id",
                            None,
                        )
                        if fname:
                            fields.append({"name": fname})
                models.append({"module": path, "class_name": n.name, "fields": fields})
    return tools, models


async def build_manifest(system: str, code_root: str) -> SystemManifest:
    aliases = await get_endpoint_aliases()
    files = sorted(set(_iter_py(code_root)))

    imports: list[tuple[str, str]] = []
    endpoints_used: list[dict] = []
    tools: list[dict] = []
    models: list[dict] = []
    events: list[dict] = []
    refs: list[ContentRef] = []

    for py in files:
        try:
            text = open(py, encoding="utf-8").read()
        except Exception:
            text = ""
        try:
            tree = ast.parse(text)
        except Exception:
            tree = None

        imports.extend(_scan_imports(py, tree))
        endpoints_used.extend(_scan_endpoints(py, text, aliases))
        t, m = _scan_tools_and_models(py, tree)
        tools.extend(t)
        models.extend(m)

        # events + header hints
        for i, line in enumerate(text.splitlines(), 1):
            m = EVENT_PUB_RE.search(line)
            if m:
                events.append({"topic": m.group("topic"), "file": py, "line": i})

        refs.append(_slice_ref(py, 1, 120))

    edges_http = [
        {"from": r["file"], "to_alias": r["alias"], "path": r.get("path")} for r in endpoints_used
    ]

    man = SystemManifest(
        system=system,
        files=files,
        imports=sorted(set(imports)),
        endpoints_used=endpoints_used,
        tools_used=tools,
        models=models,
        edges={"imports": [], "http": edges_http, "events": events, "tool": []},
        invariants=[
            "header_discipline(x-decision-id,x-budget-ms,X-Cost-MS)",
            "no_http_self_edge",
            "use_live_overlay_only",
        ],
        content_refs=refs[:64],
        examples=[],
    )
    body = json.dumps(man.model_dump(), sort_keys=True).encode("utf-8")
    man.manifest_hash = hashlib.blake2b(body, digest_size=16).hexdigest()
    man.generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return man
