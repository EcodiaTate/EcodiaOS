from __future__ import annotations

import json
from pathlib import Path

ARCHIVE = Path("/app/_simula/archive/pareto.jsonl")
ARCHIVE.parent.mkdir(parents=True, exist_ok=True)


def _write_jsonl(obj: dict):
    with open(ARCHIVE, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _read_jsonl() -> list[dict]:
    if not ARCHIVE.exists():
        return []
    return [json.loads(l) for l in ARCHIVE.read_text(encoding="utf-8").splitlines() if l.strip()]


def _dominates(a: dict, b: dict) -> bool:
    # maximize: tests_ok, static, coverage, contracts; minimize: diff_size
    return (
        (a["tests_ok"] >= b["tests_ok"])
        and (a["static"] >= b["static"])
        and (a["coverage"] >= b["coverage"])
        and (a["contracts"] >= b["contracts"])
        and (a["diff_size"] <= b["diff_size"])
        and (
            (a["tests_ok"] > b["tests_ok"])
            or (a["static"] > b["static"])
            or (a["coverage"] > b["coverage"])
            or (a["contracts"] > b["contracts"])
            or (a["diff_size"] < b["diff_size"])
        )
    )


def add_candidate(record: dict):
    """
    record = {
      "path": str, "diff": str, "tests_ok": int(0/1),
      "static": float, "coverage": float, "contracts": float, "diff_size": int,
      "notes": str
    }
    """
    _write_jsonl(record)


def top_k_similar(path: str, k: int = 3) -> list[dict]:
    """Return best Pareto-ish items for this path."""
    rows = [r for r in _read_jsonl() if r.get("path") == path]
    if not rows:
        return []
    # Fast Pareto filter
    pareto = []
    for r in rows:
        if any(_dominates(o, r) for o in rows):  # dominated
            continue
        pareto.append(r)
    # sort by (tests_ok desc, static desc, coverage desc, -diff_size)
    pareto.sort(
        key=lambda r: (r["tests_ok"], r["static"], r["coverage"], -r["diff_size"]),
        reverse=True,
    )
    return pareto[:k]
