from __future__ import annotations

from typing import Optional, TypedDict

from core.utils.neo.cypher_query import cypher_query


class LastCommitResult(TypedDict, total=False):
    updated: bool
    previous: str | None
    current: str | None


async def read_last_commit(state_id: str = "default") -> str | None:
    """
    Returns the last processed commit sha (or None).
    Idempotent and warning-free (MERGE ensures label existence).
    """
    recs = await cypher_query(
        """
        MERGE (s:IngestState {id:$id})
        ON CREATE SET s.created_at = datetime()
        RETURN s.last_commit AS last
        """,
        {"id": state_id},
    )
    return recs[0]["last"] if recs else None


async def write_last_commit(new_commit: str, state_id: str = "default") -> LastCommitResult:
    """
    Compare-and-set style update.
    - Only updates when value changes.
    - Returns {updated, previous, current}.
    """
    recs = await cypher_query(
        """
        MERGE (s:IngestState {id:$id})
        ON CREATE SET s.created_at = datetime()
        WITH s, s.last_commit AS prev, $commit AS new
        // Mutate only if changed (keeps write logs calm)
        SET s.last_commit = CASE WHEN prev IS NULL OR prev <> new THEN new ELSE s.last_commit END,
            s.updated_at  = CASE WHEN prev IS NULL OR prev <> new THEN datetime() ELSE s.updated_at END
        WITH prev, s
        RETURN prev AS previous, s.last_commit AS current
        """,
        {"id": state_id, "commit": new_commit},
    )
    previous = recs[0]["previous"] if recs else None
    current = recs[0]["current"] if recs else None
    return {"updated": previous != current, "previous": previous, "current": current}


async def check_and_mark_processed(commit_id: str, state_id: str = "default") -> bool:
    """
    Returns True if this commit_id has ALREADY been seen (dedup),
    False if this is the first time (and marks it as processed).
    Uses APOC when available for an accurate `created` flag; falls back to MERGE.
    """
    # Preferred path: APOC returns a precise `created` boolean.
    try:
        recs = await cypher_query(
            """
            CALL apoc.merge.node(
              ['IngestHistory'],
              {commit_id:$cid},
              {},
              {first_seen: datetime(), state_id: $sid}
            ) YIELD node, created
            // Track touches even if already existed
            SET node.last_seen = datetime(),
                node.count     = coalesce(node.count,0) + CASE WHEN created THEN 0 ELSE 1 END
            RETURN created AS was_created
            """,
            {"cid": commit_id, "sid": state_id},
        )
        was_created = recs[0]["was_created"] if recs else False
        return not was_created  # already processed == not created now
    except Exception:
        # Fallback: pure Cypher MERGE (no `created` flag), infer via OPTIONAL MATCH
        recs = await cypher_query(
            """
            OPTIONAL MATCH (h:IngestHistory {commit_id:$cid})
            WITH h, $cid AS cid, $sid AS sid
            MERGE (h2:IngestHistory {commit_id:cid})
            ON CREATE SET h2.first_seen = datetime(), h2.state_id = sid
            ON MATCH  SET h2.last_seen  = datetime(), h2.count = coalesce(h2.count,0) + 1
            RETURN h IS NOT NULL AS existed_before
            """,
            {"cid": commit_id, "sid": state_id},
        )
        existed_before = recs[0]["existed_before"] if recs else False
        return existed_before
