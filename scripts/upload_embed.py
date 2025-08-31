# scripts/ingest_salience_exemplars.py
from __future__ import annotations

import argparse
import asyncio
import csv
import glob
import json
import os
import random
import re
import sys
import uuid
from dataclasses import dataclass

# Embeddings (Gemini 3072-dim vectors)
from core.llm.embeddings_gemini import get_embedding  # -> returns List[float]

# Driverless Cypher executor (auto-resolves driver via get_driver internally)
from core.utils.neo.cypher_query import cypher_query

LABEL = "SemanticExemplar"
VECTOR_PROP = "vector_gemini"
INDEX_NAME = "semantic_exemplar_vector_gemini_3072_cosine"
UNIQUE_KEY = "uuid"

CREATE_CONSTRAINT_UUID = f"""
CREATE CONSTRAINT {LABEL.lower()}_{UNIQUE_KEY}_uniq IF NOT EXISTS
FOR (n:{LABEL}) REQUIRE n.{UNIQUE_KEY} IS UNIQUE
"""

CREATE_VECTOR_INDEX = f"""
CREATE VECTOR INDEX {INDEX_NAME} IF NOT EXISTS
FOR (n:{LABEL}) ON (n.{VECTOR_PROP})
OPTIONS {{
  indexConfig: {{
    `vector.dimensions`: 3072,
    `vector.similarity_function`: 'cosine'
  }}
}}
"""

UPSERT_NODE = f"""
MERGE (n:{LABEL} {{ {UNIQUE_KEY}: $uuid }})
SET n.scorer     = $scorer,
    n.text       = $text,
    n.category   = CASE WHEN $category = "" THEN n.category ELSE $category END,
    n.rationale  = CASE WHEN $rationale = "" THEN n.rationale ELSE $rationale END,
    n.tags       = CASE WHEN $tags IS NULL THEN n.tags ELSE $tags END,
    n.updated_at = datetime()
SET n.{VECTOR_PROP} = $vec
RETURN n.{UNIQUE_KEY} AS uuid
"""

FILENAME_SCORER_RE = re.compile(r"([^/\\]+?)[-_]salience_cases", re.IGNORECASE)


@dataclass
class Row:
    text: str
    category: str
    rationale: str
    scorer: str
    tags: list[str] | None = None  # optional


def infer_scorer_from_filename(path: str) -> str:
    name = os.path.basename(path)
    m = FILENAME_SCORER_RE.search(name)
    return (m.group(1) if m else "unknown").strip()


def parse_tags(val: str | None) -> list[str] | None:
    if val is None:
        return None
    s = val.strip()
    if not s:
        return None
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    # comma separated fallback
    return [t.strip() for t in s.split(",") if t.strip()]


def read_rows_from_csv(path: str) -> list[Row]:
    file_scorer = infer_scorer_from_filename(path)
    out: list[Row] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return out
        cols = {c.lower(): c for c in reader.fieldnames}
        text_c = cols.get("text")
        cat_c = cols.get("category")
        rat_c = cols.get("rationale")
        tags_c = cols.get("tags")  # optional
        scorer_c = cols.get("scorer")  # prefer CSV column if present

        if not text_c:
            raise ValueError(f"{path}: missing required column 'text'")

        for r in reader:
            text = (r.get(text_c) or "").strip()
            if not text:
                continue
            category = (r.get(cat_c) or "").strip() if cat_c else ""
            rationale = (r.get(rat_c) or "").strip() if rat_c else ""
            tags = parse_tags(r.get(tags_c)) if tags_c else None
            scorer_val = (r.get(scorer_c) or "").strip() if scorer_c else ""
            scorer = scorer_val if scorer_val else file_scorer
            out.append(
                Row(text=text, category=category, rationale=rationale, scorer=scorer, tags=tags),
            )
    return out


def stable_uuid(scorer: str, text: str) -> str:
    # Deterministic ID so re-runs don't duplicate
    base = f"{scorer}||{text}".encode()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base.hex()))


async def ensure_schema() -> None:
    # Driverless cypher calls
    await cypher_query(CREATE_CONSTRAINT_UUID, {})
    await cypher_query(CREATE_VECTOR_INDEX, {})
    print(f"✅ Schema ready: unique({LABEL}.{UNIQUE_KEY}), vector index {INDEX_NAME}")


async def retry_get_embedding(
    text: str,
    *,
    max_retries: int = 6,
    base_delay: float = 0.8,
) -> list[float]:
    """
    Gemini can throw 500 INTERNAL when hammered. Retry with exponential backoff + jitter.
    """
    attempt = 0
    while True:
        try:
            return await get_embedding(text)
        except Exception as e:
            attempt += 1
            msg = str(e)
            # Retry on 5xx or explicit INTERNAL markers; otherwise re-raise
            retryable = (
                ("INTERNAL" in msg) or ("500" in msg) or ("temporarily unavailable" in msg.lower())
            )
            if not retryable or attempt > max_retries:
                raise
            sleep_s = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.4)
            print(
                f"↻ Embedding retry {attempt}/{max_retries} after {sleep_s:.1f}s (reason: {msg[:160]})",
                file=sys.stderr,
            )
            await asyncio.sleep(sleep_s)


async def upsert_batch(rows: list[Row], concurrency: int = 4, progress_every: int = 100) -> int:
    sem = asyncio.Semaphore(concurrency)
    count = 0
    failed: list[Row] = []

    async def _do(row: Row):
        nonlocal count
        try:
            async with sem:
                vec = await retry_get_embedding(row.text)
                params = {
                    "uuid": stable_uuid(row.scorer, row.text),
                    "scorer": row.scorer,
                    "text": row.text,
                    "category": row.category or "",
                    "rationale": row.rationale or "",
                    "tags": row.tags,  # None or list[str]
                    "vec": vec,
                }
                res = await cypher_query(UPSERT_NODE, params)
                if res:
                    count += 1
                    if count % progress_every == 0:
                        print(f"… upserted {count}", flush=True)
        except Exception as e:
            failed.append(row)
            print(f"⚠️ Upsert failed ({row.scorer}): {e}", file=sys.stderr)

    await asyncio.gather(*(_do(r) for r in rows))

    # write failures for easy retry
    if failed:
        os.makedirs("data", exist_ok=True)
        fail_path = "data/failed_rows.csv"
        with open(fail_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["text", "category", "rationale", "scorer", "tags"])
            w.writeheader()
            for r in failed:
                w.writerow(
                    {
                        "text": r.text,
                        "category": r.category,
                        "rationale": r.rationale,
                        "scorer": r.scorer,
                        "tags": json.dumps(r.tags) if r.tags is not None else "",
                    },
                )
        print(
            f"❗ {len(failed)} rows failed. Wrote to {fail_path}. Re-run with --input-glob {fail_path}",
        )

    return count


def dedupe_rows(rows: list[Row]) -> list[Row]:
    seen = set()
    out: list[Row] = []
    for r in rows:
        key = (r.scorer, r.text, r.category, r.rationale, tuple(r.tags or []))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def write_merged_csv(rows: list[Row], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["text", "category", "rationale", "scorer", "tags"])
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "text": r.text,
                    "category": r.category,
                    "rationale": r.rationale,
                    "scorer": r.scorer,
                    "tags": json.dumps(r.tags) if r.tags is not None else "",
                },
            )


async def main():
    p = argparse.ArgumentParser(
        description="Merge salience case CSVs, embed, and upsert as :SemanticExemplar.",
    )
    p.add_argument("--input-glob", default="*_salience_cases*.csv", help="Glob for input CSVs")
    p.add_argument(
        "--write-merged-csv",
        help="Optional path to write merged CSV (text,category,rationale,scorer,tags)",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Embedding/upsert concurrency (default 4)",
    )
    args = p.parse_args()

    files = sorted(glob.glob(args.input_glob))
    if not files:
        print(f"No files matched: {args.input_glob}")
        return

    print(f"🔎 Found {len(files)} files")
    all_rows: list[Row] = []
    for fp in files:
        try:
            rows = read_rows_from_csv(fp)
            inferred = infer_scorer_from_filename(fp)
            print(
                f"  • {os.path.basename(fp)} -> {len(rows)} rows (scorer from CSV if present; fallback='{inferred}')",
            )
            all_rows.extend(rows)
        except Exception as e:
            print(f"✖ {fp}: {e}", file=sys.stderr)

    if not all_rows:
        print("No rows to process.")
        return

    # Dedupe exact duplicates
    all_rows = dedupe_rows(all_rows)
    print(f"🧹 Deduped to {len(all_rows)} rows")

    if args.write_merged_csv:
        write_merged_csv(all_rows, args.write_merged_csv)
        print(f"📝 Merged CSV written to {args.write_merged_csv}")

    # No explicit driver init/close — cypher_query resolves the driver internally.
    await ensure_schema()
    upserted = await upsert_batch(all_rows, concurrency=args.concurrency)
    print(f"✅ Upserted {upserted} {LABEL} nodes")


if __name__ == "__main__":
    asyncio.run(main())
