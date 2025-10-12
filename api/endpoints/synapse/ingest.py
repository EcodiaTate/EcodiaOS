# systems/synapse/api/ingest.py
# FULLY REVISED - WITH CORRECT REWARD LOGIC INTEGRATION

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import aiofiles
from fastapi import APIRouter, HTTPException
from pydantic import ConfigDict

from core.llm.bus import event_bus
from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry import arm_registry

# --- FIX: Import the reward arbiter singleton ---
from systems.synapse.core.reward import reward_arbiter
from systems.synapse.qd.map_elites import qd_archive
from systems.synapse.qd.replicator import replicator
from systems.synapse.schemas import (
    LogOutcomeRequest as _LogOutcomeRequest,
)
from systems.synapse.schemas import (
    LogOutcomeResponse as _LogOutcomeResponse,
)
from systems.synapse.schemas import (
    PreferenceIngest as _PreferenceIngest,
)

ingest_router = APIRouter(tags=["Synapse Ingest"])
logger = logging.getLogger(__name__)

# --- Local Telemetry Logging Configuration ---
LOG_DIR = Path(os.getenv("SYNAPSE_LOG_DIR", ".synapse/logs/"))
OUTCOMES_LOG_PATH = LOG_DIR / "outcomes.jsonl"
_log_lock = asyncio.Lock()


# --- Safe local schema shims (unchanged) ---
class LogOutcomeRequest(_LogOutcomeRequest):
    model_config = ConfigDict(extra="ignore")


class LogOutcomeResponse(_LogOutcomeResponse):
    model_config = ConfigDict(extra="ignore")


class PreferenceIngest(_PreferenceIngest):
    model_config = ConfigDict(extra="ignore")


# --- Utilities (unchanged) ---
def _extract_arm_id(metrics: dict[str, Any] | None) -> str | None:
    if not isinstance(metrics, dict):
        return None
    return metrics.get("chosen_arm_id") or metrics.get("arm_id")


async def _event_publish_compat(topic: str, payload: dict[str, Any]) -> bool:
    bus = event_bus
    for meth in ("publish", "emit"):
        fn = getattr(bus, meth, None)
        if not fn:
            continue
        try:
            res = fn(topic=topic, payload=payload)
            if inspect.isawaitable(res):
                await res
            return True
        except (TypeError, Exception):
            pass
    return False


async def _log_outcome_to_file(data: dict):
    """Asynchronously appends a structured log entry to the local outcomes file."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_line = json.dumps(data, default=str) + "\n"
        async with _log_lock:
            async with aiofiles.open(OUTCOMES_LOG_PATH, mode="a", encoding="utf-8") as f:
                await f.write(log_line)
    except Exception as e:
        logger.error(f"[Telemetry] Failed to write outcome to local log file: {e}")


# --- Endpoints ---
@ingest_router.post("/outcome", response_model=LogOutcomeResponse)
async def log_outcome(req: LogOutcomeRequest) -> LogOutcomeResponse:
    logger.info(f"[API] /ingest/outcome episode={req.episode_id} task={req.task_key}")

    # --- FIX: Replace the recursive call with a call to the imported reward_arbiter logic ---
    # NOTE: Assuming the standalone `log_outcome` function from reward.py should be a method of the RewardArbiter class.
    scalar_reward, reward_vector = await reward_arbiter.log_outcome(
        episode_id=req.episode_id,
        task_key=req.task_key,
        metrics=req.metrics,
        simulator_prediction=req.simulator_prediction,
    )
    # --- END FIX ---

    arm_id = _extract_arm_id(req.metrics)

    if arm_id:
        arm = arm_registry.get_arm(arm_id)
        if not arm and arm_id.startswith("dyn::"):
            # opportunistic in-memory registration
            try:
                reg = getattr(arm_registry, "register_dynamic", None) or getattr(
                    arm_registry, "add_dynamic", None
                )
                if reg:
                    maybe = (
                        reg(arm_id=arm_id)
                        if "arm_id" in getattr(reg, "__code__", {}).co_varnames
                        else reg(arm_id)
                    )
                    if inspect.isawaitable(maybe):
                        await maybe
                    arm = arm_registry.get_arm(arm_id)
            except Exception as e:
                logger.warning(
                    f"[API] Failed to opportunistically register dynamic arm '{arm_id}': {e}"
                )

    # --- This local file logging remains correct ---
    await _log_outcome_to_file(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "episode_id": req.episode_id,
            "task_key": req.task_key,
            "arm_id": arm_id,
            "scalar_reward": scalar_reward,
            "reward_vector": reward_vector,
            "metrics": req.metrics,
        }
    )

    if scalar_reward > 0.0:
        await _event_publish_compat(
            "synapse.episode.outcome.logged",
            {
                "episode_id": req.episode_id,
                "task_key": req.task_key,
                "reward": scalar_reward,
                "arm_id": arm_id,
            },
        )

    return LogOutcomeResponse(ack=True, ingested_at=datetime.now(UTC).isoformat())


@ingest_router.post("/preference")
async def ingest_preference(req: PreferenceIngest) -> dict[str, Any]:
    # (This endpoint is unchanged and correct)
    logger.info(f"[API] /ingest/preference winner={req.winner} loser={req.loser}")
    if not req.winner or not req.loser or req.winner == req.loser:
        raise HTTPException(status_code=400, detail="Invalid preference pair.")
    query = """
    MATCH (winner:PolicyArm {id: $winner_id})
    MATCH (loser:PolicyArm {id: $loser_id})
    CREATE (p:Preference {id: randomUUID(), source: $source, created_at: datetime()})
    MERGE (p)-[:CHOSE]->(winner)
    MERGE (p)-[:REJECTED]->(loser)
    """
    try:
        await cypher_query(
            query,
            {"winner_id": req.winner, "loser_id": req.loser, "source": req.source or "unknown"},
        )
    except Exception as e:
        logger.error(f"[API] Failed to persist preference to graph: {e}")
        raise HTTPException(status_code=500, detail="Failed to record preference.")
    await _event_publish_compat(
        "synapse.preference.ingested", {"winner": req.winner, "loser": req.loser}
    )
    return {"status": "accepted"}
