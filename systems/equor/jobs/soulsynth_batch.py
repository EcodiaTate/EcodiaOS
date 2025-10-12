# systems/equor/jobs/soulsynth_batch.py
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from datetime import UTC, datetime
from typing import Any, Dict, List

from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from core.utils.neo.cypher_query import cypher_query
from systems.equor.jobs.advanced_synthesis import gather_samples_with_strategy
from systems.voxis.core.user_profile import (
    ensure_soul_profile,
    normalize_profile_upserts_from_llm,
    upsert_soul_profile_properties,
)

# --- Configuration ---
LOOKBACK_HOURS = int(os.getenv("SOULSYNTH_LOOKBACK_HOURS", "24"))
MAX_USERS_PER_RUN = int(os.getenv("SOULSYNTH_MAX_USERS", "50"))
SAMPLES_PER_USER = int(os.getenv("SOULSYNTH_SAMPLES_PER_USER", "15"))
MIN_CONFIDENCE_WRITE = float(os.getenv("SOULSYNTH_MIN_CONF_WRITE", "0.7"))
DRY_RUN = os.getenv("SOULSYNTH_DRY_RUN", "false").lower() == "true"
CONCURRENCY_LIMIT = int(os.getenv("SOULSYNTH_CONCURRENCY", "5"))

AGENT_SCOPE = "equor.soulsynth.v1"
AGENT_NAME = "Equor.SoulSynth"
logger = logging.getLogger(__name__)


# --- Cypher Queries ---

ACTIVE_USERS_Q = """
MATCH (t:SoulInput|SoulResponse)
WHERE t.timestamp >= datetime() - duration({hours: $lookback})
  AND t.user_id IS NOT NULL
RETURN DISTINCT t.user_id AS user_id
LIMIT $limit
"""

USER_DATA_COUNT_Q = """
MATCH (si:SoulInput {user_id: $uid})-[:GENERATES]->(:SoulResponse)
RETURN count(si) AS pair_count
"""


# --- Core Logic ---


async def _get_current_profile(user_id: str) -> dict[str, Any]:
    """Fetches the user's current SoulProfile properties."""
    query = """
    MATCH (:SoulNode {uuid:$uid})-[:HAS_PROFILE]->(p:SoulProfile)
    RETURN p
    LIMIT 1
    """
    try:
        rows = await cypher_query(query, {"uid": user_id})
        if rows and rows[0] and rows[0].get("p"):
            return {
                k: v
                for k, v in rows[0]["p"].items()
                if isinstance(v, (str, int, float, bool, list))
            }
    except Exception as e:
        logger.warning(f"[_get_current_profile] Could not fetch profile for {user_id}: {e}")
    return {}


async def _get_active_user_ids(lookback_hours: int, limit: int) -> list[str]:
    """Finds user IDs with recent conversational turns."""
    rows = await cypher_query(ACTIVE_USERS_Q, {"lookback": lookback_hours, "limit": limit})
    ids = [r["user_id"] for r in rows if r.get("user_id")]
    random.shuffle(ids)
    return ids


async def _select_synthesis_strategy(user_id: str) -> str:
    """Dynamically chooses the best strategy based on available user data."""
    try:
        rows = await cypher_query(USER_DATA_COUNT_Q, {"uid": user_id})
        pair_count = rows[0]["pair_count"] if rows else 0

        if pair_count < 20:
            # For new users with little data, prioritize finding explicit, high-signal facts.
            strategy = "self_reflection"
        elif 20 <= pair_count < 100:
            # For established users, look for general topics of interest.
            strategy = "thematic_cluster"
        else:
            # For power users with lots of data, dig deep into their curiosity.
            strategy = "curiosity_probes"

        logger.info(f"[{user_id}] Data count: {pair_count} pairs. Selected strategy: '{strategy}'")
        return strategy
    except Exception as e:
        logger.warning(
            f"[{user_id}] Could not determine data count for strategy selection: {e}. Defaulting to 'thematic_cluster'."
        )
        return "thematic_cluster"


async def _synthesize_profile_for_user(user_id: str, strategy: str) -> dict[str, Any]:
    """Orchestrates the synthesis process using a pre-selected strategy."""
    current_profile = await _get_current_profile(user_id)

    samples = await gather_samples_with_strategy(
        strategy=strategy,
        user_id=user_id,
        limit=SAMPLES_PER_USER,
    )

    if not samples:
        return {"user_id": user_id, "status": "skipped_no_samples", "strategy_used": strategy}

    prompt_response = await build_prompt(
        scope=AGENT_SCOPE,
        summary="Synthesize durable profile facts from conversation samples.",
        context={
            "user_id": user_id,
            "conversation_samples": samples,
            "current_profile": current_profile,
            "synthesis_strategy": strategy,
        },
    )

    llm_response = await call_llm_service(
        prompt_response=prompt_response,
        agent_name=AGENT_NAME,
        scope=AGENT_SCOPE,
    )

    # Robust extract from llm_response
    payload = getattr(llm_response, "json", None)
    if not isinstance(payload, dict):
        text = getattr(llm_response, "text", "") or ""
        try:
            from core.llm.utils import extract_json_block

            block = extract_json_block(text or "")
            payload = json.loads(block) if block else {}
        except Exception:
            payload = {}

    updates = normalize_profile_upserts_from_llm(
        payload,
        user_id=user_id,
        min_confidence=MIN_CONFIDENCE_WRITE,
    )

    if not updates:
        return {"user_id": user_id, "status": "no_new_updates_found", "strategy_used": strategy}

    if DRY_RUN:
        return {
            "user_id": user_id,
            "status": "dry_run",
            "updates": updates,
            "strategy_used": strategy,
        }

    await ensure_soul_profile(user_id)
    props_count, facts_count = await upsert_soul_profile_properties(
        user_id=user_id,
        properties=updates,
        source=f"equor_soulsynth_{strategy}",  # Log which strategy was used
        confidence=1.0,
    )
    return {
        "user_id": user_id,
        "status": "written",
        "strategy_used": strategy,
        "props_updated": props_count,
        "facts_created": facts_count,
        "updates": updates,
    }


async def run_batch() -> dict[str, Any]:
    """Main entrypoint for the batch synthesis job."""
    start_time = time.time()
    print(
        f"[SoulSynth] Starting batch run at {datetime.now(UTC).isoformat()} with DYNAMIC strategy selection..."
    )

    user_ids = await _get_active_user_ids(LOOKBACK_HOURS, MAX_USERS_PER_RUN)
    if not user_ids:
        print("[SoulSynth] No active users found in the lookback window.")
        return {"status": "no_active_users", "t_sec": 0}

    results: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def _guarded_run(user_id: str):
        strategy = "unknown"
        async with semaphore:
            try:
                # Determine strategy *before* the main execution
                strategy = await _select_synthesis_strategy(user_id)
                # Pass the chosen strategy into the worker function
                result = await _synthesize_profile_for_user(user_id, strategy)
            except Exception as e:
                # Now, the strategy name is available even when an error occurs
                result = {
                    "user_id": user_id,
                    "status": "error",
                    "error": str(e),
                    "strategy_used": strategy,
                }
                logger.exception(
                    f"[{user_id}] SoulSynth guarded run failed during strategy '{strategy}'"
                )
            results.append(result)
            print(
                f"[SoulSynth] ...processed user {user_id}, status: {result.get('status', 'unknown')}, strategy: {result.get('strategy_used', 'N/A')}"
            )

    await asyncio.gather(*[_guarded_run(uid) for uid in user_ids])

    end_time = time.time()
    summary = {
        "start_ts": datetime.fromtimestamp(start_time, tz=UTC).isoformat(),
        "duration_sec": round(end_time - start_time, 2),
        "config": {
            "lookback_hours": LOOKBACK_HOURS,
            "max_users": MAX_USERS_PER_RUN,
            "samples_per_user": SAMPLES_PER_USER,
            "dry_run": DRY_RUN,
        },
        "results_summary": {
            "total_processed": len(results),
            "written": sum(1 for r in results if r.get("status") == "written"),
            "skipped": sum(1 for r in results if "skip" in r.get("status", "")),
            "no_updates": sum(1 for r in results if r.get("status") == "no_new_updates_found"),
            "errors": sum(1 for r in results if r.get("status") == "error"),
        },
        "results": results,
    }
    print(
        f"[SoulSynth] Batch run complete. Processed {summary['results_summary']['total_processed']} users in {summary['duration_sec']}s."
    )
    return summary


if __name__ == "__main__":
    run_summary = asyncio.run(run_batch())
    print(json.dumps(run_summary, indent=2))
