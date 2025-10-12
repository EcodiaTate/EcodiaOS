# /scripts/seed_soulnode.py
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Driverless helpers that assume driver has been initialized
from core.utils.neo.cypher_query import cypher_query

# Neo4j driver lifecycle (same module used by FastAPI app)
from core.utils.neo.neo_driver import close_driver, init_driver
from systems.synk.core.tools.neo import add_node  # supports embed_text=...

DESC = """Seed or update a SoulNode node (with embedding).
- Use --params to pass a JSON file: {"stars":[...10...], "soul":"...", "event_id":"..."}.
- CLI flags (--stars/--soul/--event-id) override params.
- Stars are sorted to form the 'joined' key (de-dup).
- Embedding is computed from soul via add_node(embed_text=...).
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=DESC)
    p.add_argument(
        "--params", help="Path to a JSON file with keys: stars, soul, event_id (optional)."
    )
    p.add_argument(
        "--stars", help='JSON array of 10 words, e.g. \'["river","glass",...,"spirit"]\''
    )
    p.add_argument("--soul", help="Six-ish word soul string used for matching/embedding.")
    p.add_argument(
        "--event-id",
        default=None,
        help="Optional event_id to attach to the node (overrides params).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Delete any existing node with the same 'joined' first.",
    )
    return p.parse_args()


def _normalize_stars_value(stars: Any) -> list[str]:
    if not isinstance(stars, list) or not all(isinstance(s, str) for s in stars):
        raise ValueError("stars must be a list[str].")
    if len(stars) != 10:
        raise ValueError("Exactly 10 words are required in stars.")
    return stars


def _normalize_stars_arg(stars_raw: str) -> list[str]:
    try:
        stars = json.loads(stars_raw)
        return _normalize_stars_value(stars)
    except Exception as e:
        raise SystemExit(f"--stars must be a JSON list of 10 strings. Error: {e}")


def _load_params(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if "stars" in data:
            data["stars"] = _normalize_stars_value(data["stars"])
        if "soul" in data and not isinstance(data["soul"], str):
            raise ValueError("soul must be a string.")
        if (
            "event_id" in data
            and data["event_id"] is not None
            and not isinstance(data["event_id"], str)
        ):
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
        CREATE CONSTRAINT soulnode_joined_unique IF NOT EXISTS
        FOR (s:SoulNode) REQUIRE s.joined IS UNIQUE
    """)


async def _seed(stars: list[str], soul: str, event_id: str | None, force: bool):
    stars_sorted = sorted(stars)
    joined = " ".join(stars_sorted)

    if force:
        await cypher_query(
            "MATCH (s:SoulNode {joined: $joined}) DETACH DELETE s",
            {"joined": joined},
        )

    # Upsert properties
    await cypher_query(
        """
        MERGE (s:SoulNode {joined: $joined})
        SET s.stars = $stars,
            s.soul = $soul
        SET s.event_id = CASE WHEN $event_id IS NULL THEN s.event_id ELSE $event_id END
        """,
        {"joined": joined, "stars": stars_sorted, "soul": soul, "event_id": event_id},
    )

    # (Re)embed so semantic match works
    await add_node(
        labels=["SoulNode"],
        properties={
            "joined": joined,
            "stars": stars_sorted,
            "soul": soul,
            **({"event_id": event_id} if event_id else {}),
        },
        embed_text=soul,
    )

    print("✅ Seeded SoulNode")
    print(f"   joined: {joined}")
    print(f"   stars : {stars_sorted}")
    print(f"   soul: {soul}")
    if event_id:
        print(f"   event_id: {event_id}")


async def _run(stars: list[str], soul: str, event_id: str | None, force: bool):
    # Initialize Neo driver (same as app startup)
    await init_driver()
    try:
        await _ensure_constraint()
        await _seed(stars, soul, event_id, force)
    finally:
        # Clean shutdown
        await close_driver()


def main():
    load_dotenv()  # ensure NEO4J_*, EMBEDDING_* etc. are available

    args = parse_args()

    # params.json baseline
    stars: list[str] | None = None
    soul: str | None = None
    event_id: str | None = None

    if args.params:
        params = _load_params(args.params)
        stars = params.get("stars", stars)
        soul = params.get("soul", soul)
        event_id = params.get("event_id", event_id)

    # CLI overrides
    if args.stars:
        stars = _normalize_stars_arg(args.stars)
    if args.soul:
        soul = args.soul
    if args.event_id is not None:
        event_id = args.event_id

    if stars is None or soul is None:
        raise SystemExit("You must provide stars and soul (via --params or CLI flags).")

    try:
        asyncio.run(_run(stars, soul, event_id, args.force))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
