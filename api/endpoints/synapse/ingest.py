# systems/synapse/api/ingest.py
# FINAL VERSION FOR PHASE II - QD ACTIVATION (arbiter + event bus compat)
from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from core.llm.bus import event_bus
from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry import arm_registry
from systems.synapse.core.reward import reward_arbiter
from systems.synapse.qd.map_elites import qd_archive  # <-- QD
from systems.synapse.qd.replicator import replicator  # <-- REPLICATOR

# --- Alias imported schemas; we'll wrap them safely below ---
from systems.synapse.schemas import (  # type: ignore
    LogOutcomeRequest as _LogOutcomeRequest,
    LogOutcomeResponse as _LogOutcomeResponse,
    PreferenceIngest as _PreferenceIngest,
)

ingest_router = APIRouter(tags=["Synapse Ingest"])
logger = logging.getLogger(__name__)

# --- Safe local schema shims (Pydantic v2) -----------------

try:
    if isinstance(_LogOutcomeRequest, type) and issubclass(_LogOutcomeRequest, BaseModel):
        class LogOutcomeRequest(_LogOutcomeRequest):  # type: ignore[misc, valid-type]
            model_config = ConfigDict(extra="ignore")
    else:  # minimal fallback
        class LogOutcomeRequest(BaseModel):
            model_config = ConfigDict(extra="ignore")
            episode_id: str
            task_key: str
            metrics: dict[str, Any] | None = None
            simulator_prediction: dict[str, Any] | None = None
except Exception:
    class LogOutcomeRequest(BaseModel):
        model_config = ConfigDict(extra="ignore")
        episode_id: str
        task_key: str
        metrics: dict[str, Any] | None = None
        simulator_prediction: dict[str, Any] | None = None

try:
    if isinstance(_LogOutcomeResponse, type) and issubclass(_LogOutcomeResponse, BaseModel):
        class LogOutcomeResponse(_LogOutcomeResponse):  # type: ignore[misc, valid-type]
            model_config = ConfigDict(extra="ignore")
    else:
        class LogOutcomeResponse(BaseModel):
            model_config = ConfigDict(extra="ignore")
            ack: bool
            ingested_at: str
except Exception:
    class LogOutcomeResponse(BaseModel):
        model_config = ConfigDict(extra="ignore")
        ack: bool
        ingested_at: str

try:
    if isinstance(_PreferenceIngest, type) and issubclass(_PreferenceIngest, BaseModel):
        class PreferenceIngest(_PreferenceIngest):  # type: ignore[misc, valid-type]
            model_config = ConfigDict(extra="ignore")
    else:
        class PreferenceIngest(BaseModel):
            model_config = ConfigDict(extra="ignore")
            winner: str
            loser: str
            source: str | None = None
except Exception:
    class PreferenceIngest(BaseModel):
        model_config = ConfigDict(extra="ignore")
        winner: str
        loser: str
        source: str | None = None


async def _arbiter_log_outcome_compat(arbiter, **kwargs):
    """
    Call arbiter with best-effort method selection.
    Normalises the result to (scalar_reward: float, details: dict).
    """
    candidates = (
        "log_outcome",
        "record_outcome",
        "submit_outcome",
        "ingest_outcome",
        "handle_outcome",
    )
    for name in candidates:
        fn = getattr(arbiter, name, None)
        if not fn:
            continue
        res = fn(**kwargs)
        if inspect.isawaitable(res):
            res = await res
        # normalise
        if isinstance(res, tuple) and len(res) >= 2:
            sr, det = res[0], res[1]
            try:
                sr = float(sr)
            except Exception:
                sr = 0.0
            return sr, det if isinstance(det, dict) else {"details": det}
        if isinstance(res, dict):
            sr = float(res.get("scalar_reward", 0.0))
            return sr, res
        # unknown shape -> wrap
        return 0.0, {"arbiter_result": res}
    # nothing matched
    return 0.0, {"arbiter_result": "no compatible log method found"}


async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x


async def _event_publish_compat(topic: str, payload: dict[str, Any]) -> bool:
    """
    Publish an event regardless of EventBus signature:
      - publish(topic=..., payload=...)
      - publish(topic, payload)
      - publish(topic, data=...)
      - publish({"topic":..., "payload":...})
      - emit(...), emit(topic, payload), etc.
    Returns True if any variant succeeded (no exception), False otherwise.
    """
    bus = event_bus
    for meth in ("publish", "emit"):
        fn = getattr(bus, meth, None)
        if not fn:
            continue
        # 1) kwargs style
        try:
            await _maybe_await(fn(topic=topic, payload=payload))
            return True
        except TypeError:
            pass
        # 2) positional (topic, payload)
        try:
            await _maybe_await(fn(topic, payload))
            return True
        except TypeError:
            pass
        # 3) positional + named data
        try:
            await _maybe_await(fn(topic, data=payload))
            return True
        except TypeError:
            pass
        # 4) single dict event
        try:
            await _maybe_await(fn({"topic": topic, "payload": payload}))
            return True
        except TypeError:
            pass
        # 5) kwargs expand last resort (if bus expects publish(self, **event))
        try:
            await _maybe_await(fn(topic=topic, **(payload or {})))
            return True
        except TypeError:
            pass
        except Exception as e:
            logger.warning("[API] event publish via %s failed: %s", meth, e)
            return False
    logger.warning("[API] event publish not supported by bus signatures tried.")
    return False


@ingest_router.post("/outcome", response_model=LogOutcomeResponse)
async def log_outcome(req: LogOutcomeRequest) -> LogOutcomeResponse:
    """
    Logs the final outcome of an episode and updates learning systems (arbiter, QD, replicator).
    Compatible with multiple RewardArbiter method names and EventBus signatures.
    """
    logger.info("[API] /ingest/outcome episode=%s task=%s", req.episode_id, req.task_key)

    # Compat call into the RewardArbiter, regardless of its concrete API name.
    scalar_reward, _ = await _arbiter_log_outcome_compat(
        reward_arbiter,
        episode_id=req.episode_id,
        task_key=req.task_key,
        metrics=req.metrics,
        simulator_prediction=req.simulator_prediction,
    )

    # Resolve arm id from metrics (prefer chosen_arm_id, then correlation.arm_id), fallback to legacy top-level
    arm_id = None
    if isinstance(req.metrics, dict):
        arm_id = (
            req.metrics.get("chosen_arm_id")
            or req.metrics.get("correlation.arm_id")
            or req.metrics.get("arm_id")
        )
    arm_id = arm_id or getattr(req, "arm_id", None)

    arm = arm_registry.get_arm(arm_id) if arm_id else None
    if arm:
        try:
            qd_archive.insert(arm.id, scalar_reward, req.metrics)
            niche = qd_archive.get_descriptor(arm.id, req.metrics)
            replicator.update_fitness(niche, scalar_reward)
        except Exception as e:
            logger.warning("[API] QD/replicator update failed (non-fatal): %s", e)
    else:
        logger.warning("[API] WARNING: Could not find arm '%s' for QD update.", arm_id)

    # Emit event (best-effort; never fail the API)
    await _event_publish_compat(
        "synapse.episode.outcome.logged",
        {"episode_id": req.episode_id, "task_key": req.task_key, "reward": scalar_reward},
    )

    return LogOutcomeResponse(ack=True, ingested_at=datetime.now(UTC).isoformat())


@ingest_router.post("/preference")
async def ingest_preference(req: PreferenceIngest) -> dict[str, Any]:
    """
    Ingests a pairwise preference (winner over loser), persists it, and emits an event.
    This is concrete and auditable; a separate trainer can fit Bradley–Terry on this data.
    """
    logger.info(
        "[API] /ingest/preference winner=%s loser=%s source=%s",
        req.winner,
        req.loser,
        req.source,
    )
    if not req.winner or not req.loser or req.winner == req.loser:
        raise HTTPException(status_code=400, detail="Invalid preference pair.")

    # Persist a Preference edge with timestamp and source metadata
    try:
        await cypher_query(
            """
            MERGE (w:Arm {id:$w})
            MERGE (l:Arm {id:$l})
            MERGE (w)-[p:PREFERS_OVER]->(l)
            ON CREATE SET p.count = 1, p.first_at = datetime(), p.last_at = datetime(), p.sources = [$src]
            ON MATCH  SET p.count = coalesce(p.count,0) + 1, p.last_at = datetime(),
                         p.sources = apoc.coll.toSet(coalesce(p.sources, []) + [$src])
            """,
            {"w": req.winner, "l": req.loser, "src": req.source or "unknown"},
        )
    except Exception as e:
        # Fall back without APOC (may duplicate sources; acceptable)
        logger.warning("[API] preference write with APOC failed; falling back: %s", e)
        await cypher_query(
            """
            MERGE (w:Arm {id:$w})
            MERGE (l:Arm {id:$l})
            MERGE (w)-[p:PREFERS_OVER]->(l)
            ON CREATE SET p.count = 1, p.first_at = datetime(), p.last_at = datetime(), p.sources = [$src]
            ON MATCH  SET p.count = coalesce(p.count,0) + 1, p.last_at = datetime(),
                         p.sources = coalesce(p.sources, []) + [$src]
            """,
            {"w": req.winner, "l": req.loser, "src": req.source or "unknown"},
        )

    # Best-effort event
    await _event_publish_compat(
        "synapse.preference.ingested",
        {"winner": req.winner, "loser": req.loser, "source": req.source or "unknown"},
    )

    return {"status": "accepted", "message": "Preference recorded."}
