# /scripts/seed_soulphrase.py
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import List, Optional, Any, Dict

from dotenv import load_dotenv

# Neo4j driver lifecycle (same module used by FastAPI app)
from core.utils.neo.neo_driver import init_driver, close_driver

# Driverless helpers that assume driver has been initialized
from core.utils.neo.cypher_query import cypher_query
from systems.synk.core.tools.neo import add_node  # supports embed_text=...

DESC = """Seed or update a SoulPhrase node (with embedding).
- Use --params to pass a JSON file: {"stars":[...10...], "phrase":"...", "event_id":"..."}.
- CLI flags (--stars/--phrase/--event-id) override params.
- Stars are sorted to form the 'joined' key (de-dup).
- Embedding is computed from phrase via add_node(embed_text=...).
"""

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=DESC)
    p.add_argument("--params", help="Path to a JSON file with keys: stars, phrase, event_id (optional).")
    p.add_argument("--stars", help='JSON array of 10 words, e.g. \'["river","glass",...,"spirit"]\'')
    p.add_argument("--phrase", help="Six-ish word phrase string used for matching/embedding.")
    p.add_argument("--event-id", default=None, help="Optional event_id to attach to the node (overrides params).")
    p.add_argument("--force", action="store_true", help="Delete any existing node with the same 'joined' first.")
    return p.parse_args()

def _normalize_stars_value(stars: Any) -> List[str]:
    if not isinstance(stars, list) or not all(isinstance(s, str) for s in stars):
        raise ValueError("stars must be a list[str].")
    if len(stars) != 10:
        raise ValueError("Exactly 10 words are required in stars.")
    return stars

def _normalize_stars_arg(stars_raw: str) -> List[str]:
    try:
        stars = json.loads(stars_raw)
        return _normalize_stars_value(stars)
    except Exception as e:
        raise SystemExit(f"--stars must be a JSON list of 10 strings. Error: {e}")

def _load_params(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "stars" in data:
            data["stars"] = _normalize_stars_value(data["stars"])
        if "phrase" in data and not isinstance(data["phrase"], str):
            raise ValueError("phrase must be a string.")
        if "event_id" in data and data["event_id"] is not None and not isinstance(data["event_id"], str):
            raise ValueError("event_id must be a string if provided.")
        return data
    except FileNotFoundError:
        raise SystemExit(f"Params file not found: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in params file: {e}")
    except Exception as e:
        raise SystemExit(f"Error reading params file: {e}")

async def _ensure_constraint():
    await cypher_query("""
        CREATE CONSTRAINT soulphrase_joined_unique IF NOT EXISTS
        FOR (s:SoulPhrase) REQUIRE s.joined IS UNIQUE
    """)

async def _seed(stars: List[str], phrase: str, event_id: Optional[str], force: bool):
    stars_sorted = sorted(stars)
    joined = " ".join(stars_sorted)

    if force:
        await cypher_query(
            "MATCH (s:SoulPhrase {joined: $joined}) DETACH DELETE s",
            {"joined": joined},
        )

    # Upsert properties
    await cypher_query(
        """
        MERGE (s:SoulPhrase {joined: $joined})
        SET s.stars = $stars,
            s.phrase = $phrase
        SET s.event_id = CASE WHEN $event_id IS NULL THEN s.event_id ELSE $event_id END
        """,
        {"joined": joined, "stars": stars_sorted, "phrase": phrase, "event_id": event_id},
    )

    # (Re)embed so semantic match works
    await add_node(
        labels=["SoulPhrase"],
        properties={
            "joined": joined,
            "stars": stars_sorted,
            "phrase": phrase,
            **({"event_id": event_id} if event_id else {}),
        },
        embed_text=phrase,
    )

    print("✅ Seeded SoulPhrase")
    print(f"   joined: {joined}")
    print(f"   stars : {stars_sorted}")
    print(f"   phrase: {phrase}")
    if event_id:
        print(f"   event_id: {event_id}")

async def _run(stars: List[str], phrase: str, event_id: Optional[str], force: bool):
    # Initialize Neo driver (same as app startup)
    await init_driver()
    try:
        await _ensure_constraint()
        await _seed(stars, phrase, event_id, force)
    finally:
        # Clean shutdown
        await close_driver()

def main():
    load_dotenv()  # ensure NEO4J_*, EMBEDDING_* etc. are available

    args = parse_args()

    # params.json baseline
    stars: Optional[List[str]] = None
    phrase: Optional[str] = None
    event_id: Optional[str] = None

    if args.params:
        params = _load_params(args.params)
        stars = params.get("stars", stars)
        phrase = params.get("phrase", phrase)
        event_id = params.get("event_id", event_id)

    # CLI overrides
    if args.stars:
        stars = _normalize_stars_arg(args.stars)
    if args.phrase:
        phrase = args.phrase
    if args.event_id is not None:
        event_id = args.event_id

    if stars is None or phrase is None:
        raise SystemExit("You must provide stars and phrase (via --params or CLI flags).")

    try:
        asyncio.run(_run(stars, phrase, event_id, args.force))
    except KeyboardInterrupt:
        sys.exit(130)

if __name__ == "__main__":
    main()
