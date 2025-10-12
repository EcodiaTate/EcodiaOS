# api/endpoints/simula/_helpers.py
import re
from pathlib import Path
from typing import Optional, Tuple

from systems.simula.schema import SimulaCodegenTarget

# ==============================================================================
# Helper functions for parsing the API request
# ==============================================================================


def _to_graph_fqn(path: str, symbol: str | None) -> str | None:
    if not path:
        return None
    p = path.strip().replace("\\", "/").lstrip("/")
    return f"{p}::{symbol}" if symbol else p


def _path_to_module(path: str) -> str:
    p = (path or "").strip().strip("/").replace("\\", "/")
    if p.endswith(".py"):
        p = p[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def _guess_symbol_from_file(path: str, spec: str) -> str | None:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception:
        return None
    names = set(re.findall(r"^\s*(?:class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.MULTILINE))
    if not names:
        return None
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", spec or "")
    for tok in tokens:
        if tok in names:
            return tok
    lower_names = {n.lower(): n for n in names}
    for tok in tokens:
        if tok.lower() in lower_names:
            return lower_names[tok.lower()]
    return None


def _derive_target_fqn(
    targets: list[SimulaCodegenTarget], spec: str
) -> tuple[str | None, str | None, str | None]:
    if not targets:
        return None, None, None
    t0 = targets[0]
    mod = _path_to_module(t0.path)
    if not mod:
        return None, None, t0.path or None
    sym = t0.signature or _guess_symbol_from_file(t0.path, spec)
    graph_fqn = _to_graph_fqn(t0.path, sym)
    dotted = f"{mod}.{sym}" if sym else mod
    return graph_fqn, dotted, t0.path
