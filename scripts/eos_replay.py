# scripts/eos_replay.py
"""
Usage:
    python scripts/eos_replay.py --barcode <BARCODE> [--type why|capsule]
    python scripts/eos_replay.py --decision <DECISION_ID>

Reads WhyTrace/ReplayCapsule JSONL by barcode or decision_id,
replays a light salience+FAE calculation with fixed seeds, and prints uplift-esque stats.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

LEDGER_DIR = Path("data/atune_ledger")


def _find_files_for_decision(decision_id: str) -> tuple[Path | None, Path | None]:
    why = None
    cap = None
    for p in LEDGER_DIR.glob("why-*.jsonl"):
        with open(p, encoding="utf-8") as f:
            try:
                j = json.loads(f.readline())
                if j.get("decision_id") == decision_id:
                    why = p
                    break
            except Exception:
                pass
    for p in LEDGER_DIR.glob("capsule-*.jsonl"):
        with open(p, encoding="utf-8") as f:
            try:
                j = json.loads(f.readline())
                if j.get("decision_id") == decision_id:
                    cap = p
                    break
            except Exception:
                pass
    return why, cap


def _load_by_barcode(barcode: str, kind: str) -> dict[str, Any]:
    matches = list(LEDGER_DIR.glob(f"{kind}-{barcode}.jsonl"))
    if not matches:
        raise FileNotFoundError(f"No {kind} file for barcode {barcode}")
    with open(matches[0], encoding="utf-8") as f:
        return json.loads(f.readline())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--barcode", type=str, help="Barcode hash (without prefix)")
    ap.add_argument("--type", type=str, default="why", choices=["why", "capsule"])
    ap.add_argument("--decision", type=str, help="Decision ID")
    args = ap.parse_args()

    if args.decision:
        why_path, cap_path = _find_files_for_decision(args.decision)
        if not why_path or not cap_path:
            raise SystemExit("Decision ID not found in ledger.")
        with open(why_path, encoding="utf-8") as f:
            why = json.loads(f.readline())
        with open(cap_path, encoding="utf-8") as f:
            capsule = json.loads(f.readline())
    else:
        doc = _load_by_barcode(args.barcode, args.type)
        if args.type == "why":
            why = doc
            # try to find capsule by decision_id
            _, cap_path = _find_files_for_decision(why["decision_id"])
            if not cap_path:
                raise SystemExit("Capsule not found for decision.")
            with open(cap_path, encoding="utf-8") as f:
                capsule = json.loads(f.readline())
        else:
            capsule = doc
            why_path, _ = _find_files_for_decision(capsule["decision_id"])
            if not why_path:
                raise SystemExit("WhyTrace not found for decision.")
            with open(why_path, encoding="utf-8") as f:
                why = json.loads(f.readline())

    # Deterministic replay sketch: use token count to derive utility proxy
    events = capsule["inputs"]["events"]
    random.seed(capsule["decision_id"])
    util = 0.0
    for e in events:
        txts = e.get("parsed", {}).get("text_blocks", [])
        tok = sum(len(t.split()) for t in txts)
        util += min(1.0, 0.001 * tok)

    # Print a concise summary
    print(f"Decision: {capsule['decision_id']}")
    print(f"Hotspots: {why['salience'].get('hotspots')}")
    print(f"Per-head p-values: {why['salience'].get('per_head_pvals')}")
    print(f"Market: {why.get('market')}")
    print(f"Replay utility proxy: {util:.4f}")


if __name__ == "__main__":
    main()
