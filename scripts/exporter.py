# scripts/export_exemplars_csv.py
from __future__ import annotations

import argparse
import csv
import os
from typing import Any

from core.utils.neo.cypher_query import cypher_query  # ✅ driverless Neo

# Minimal fields requested
FIELDS = ["text", "category", "rationale", "scorer"]

CYPHER_TEMPLATE = """
MATCH (e:{label})
RETURN
  e.text      AS text,
  e.category  AS category,
  e.rationale AS rationale,
  e.scorer    AS scorer
LIMIT $limit
"""


async def export(label: str, out_path: str, limit: int) -> int:
    # Driverless query via cypher_query
    cypher = CYPHER_TEMPLATE.format(label=label)
    rows = await cypher_query(cypher, {"limit": int(limit)})

    # Normalize to the 4 fields, empty string if missing
    normalized: list[dict[str, Any]] = []
    for r in rows or []:
        normalized.append(
            {
                "text": (r.get("text") or "").strip(),
                "category": (r.get("category") or "").strip(),
                "rationale": (r.get("rationale") or "").strip(),
                "scorer": (r.get("scorer") or "").strip(),
            },
        )

    # Ensure dir exists
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in normalized:
            # Skip rows with empty text to avoid junk
            if not row["text"]:
                continue
            w.writerow(row)
            written += 1

    return written


async def main():
    ap = argparse.ArgumentParser(
        description="Export exemplars to CSV with fields: text,category,rationale,scorer",
    )
    ap.add_argument(
        "--label",
        default="ScorerExemplar",
        help="Node label to export (e.g., ScorerExemplar or SemanticExemplar)",
    )
    ap.add_argument("--output", default="data/exported_exemplars.csv", help="Output CSV path")
    ap.add_argument("--limit", type=int, default=1_000_000, help="Max rows to export")
    args = ap.parse_args()

    n = await export(args.label, args.output, args.limit)
    print(f"✅ Exported {n} rows from :{args.label} to {args.output}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
