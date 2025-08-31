from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

trace_router = APIRouter()
LEDGER_DIR = Path("data/atune_ledger")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _latest_match(kind: str, decision_id: str) -> dict[str, Any] | None:
    matches: list[tuple[Path, dict[str, Any]]] = []
    if not LEDGER_DIR.exists():
        return None
    for p in LEDGER_DIR.glob(f"{kind}-*.jsonl"):
        for rec in _read_jsonl(p):
            if str(rec.get("decision_id", "")) == decision_id:
                matches.append((p, rec))
    return matches[-1][1] if matches else None


@trace_router.get("/trace/{decision_id}")
async def get_trace(decision_id: str) -> dict[str, Any]:
    why = _latest_match("why", decision_id)
    cap = _latest_match("capsule", decision_id)
    if not why and not cap:
        raise HTTPException(status_code=404, detail="No trace found for decision_id")
    return {
        "decision_id": decision_id,
        "why_trace": why,  # {salience, fae_terms, probes, verdicts, market, created_utc}
        "replay_capsule": cap,  # {inputs, versions, timings, env, hashes, created_utc}
    }
