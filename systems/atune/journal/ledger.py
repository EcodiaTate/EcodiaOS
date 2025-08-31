# systems/atune/journal/ledger.py

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# ---- hash function with blake3 → blake2b fallback ----
try:
    import blake3  # type: ignore

    def _digest_hex(b: bytes) -> str:
        return blake3.blake3(b).hexdigest()
except Exception:
    import hashlib

    def _digest_hex(b: bytes) -> str:
        # Fallback keeps interface identical; switch to blake3 when available
        return hashlib.blake2b(b, digest_size=32).hexdigest()


LEDGER_DIR = Path("data/atune_ledger")
LEDGER_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class WhyTrace:
    decision_id: str
    salience: dict[str, Any]
    fae_terms: dict[str, float]
    probes: dict[str, Any]
    verdicts: dict[str, Any]
    market: dict[str, Any]
    created_utc: str


@dataclass
class ReplayCapsule:
    decision_id: str
    inputs: dict[str, Any]
    versions: dict[str, Any]
    timings: dict[str, Any]
    env: dict[str, Any]
    hashes: dict[str, str]
    created_utc: str


def _write_jsonl(name: str, obj: dict[str, Any]) -> str:
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    digest = _digest_hex(raw.encode("utf-8"))
    path = LEDGER_DIR / f"{name}-{digest}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(raw + "\n")
        f.flush()
        os.fsync(f.fileno())
    return digest  # barcode


def record(decision_id: str, why: WhyTrace, capsule: ReplayCapsule) -> dict[str, str]:
    w_barcode = _write_jsonl("why", asdict(why))
    c_barcode = _write_jsonl("capsule", asdict(capsule))
    return {"why_trace_ref": w_barcode, "replay_capsule_ref": c_barcode}
