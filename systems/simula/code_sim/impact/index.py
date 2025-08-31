# systems/simula/code_sim/impact/index.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .py_callgraph import build_callgraph

_INDEX_PATH = Path(".simula/impact_index.json")


@dataclass
class ImpactIndex:
    callgraph: dict[str, list[str]]
    symbol_tests: dict[str, list[str]]


def load_index() -> ImpactIndex:
    if _INDEX_PATH.exists():
        try:
            d = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
            return ImpactIndex(
                callgraph=d.get("callgraph") or {},
                symbol_tests=d.get("symbol_tests") or {},
            )
        except Exception:
            pass
    return ImpactIndex(callgraph={}, symbol_tests={})


def save_index(ix: ImpactIndex) -> None:
    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_PATH.write_text(
        json.dumps({"callgraph": ix.callgraph, "symbol_tests": ix.symbol_tests}, indent=2),
        encoding="utf-8",
    )


def update_callgraph(root: str = ".") -> ImpactIndex:
    ix = load_index()
    cg = build_callgraph(root)
    ix.callgraph = {k: sorted(list(v)) for k, v in cg.items()}
    save_index(ix)
    return ix


def record_symbol_tests(symbol: str, tests: list[str]) -> None:
    ix = load_index()
    st = set(ix.symbol_tests.get(symbol) or [])
    st.update(tests or [])
    ix.symbol_tests[symbol] = sorted(st)
    save_index(ix)


def k_expr_for_changed(paths: list[str]) -> str:
    ix = load_index()
    stems: set[str] = set()
    for p in paths:
        sym = Path(p).stem
        for t in ix.symbol_tests.get(sym, []):
            stems.add(Path(t).stem)
    return " or ".join(sorted(stems))[:256]
