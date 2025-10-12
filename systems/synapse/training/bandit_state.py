# systems/synapse/training/bandit_state.py
# FINAL VERSION FOR PHASE II - STATE PERSISTENCE
from __future__ import annotations

import asyncio
import logging
import threading

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry import arm_registry
from systems.synapse.schemas import PolicyArmModel as PolicyArm

logger = logging.getLogger(__name__)

# --- Dirty tracking & background flusher ---

_DIRTY: set[str] = set()
_LOCK = threading.RLock()
_flush_task: asyncio.Task | None = None
FLUSH_INTERVAL_SEC = 30.0  # Define as a constant


def mark_dirty(arm_id: str) -> None:
    """Marks an arm's bandit state as needing to be persisted."""
    with _LOCK:
        _DIRTY.add(arm_id)


def _drain_dirty(batch_size: int) -> set[str]:
    """Atomically drains a batch of dirty arm IDs."""
    with _LOCK:
        if not _DIRTY:
            return set()

        # Convert to list to safely iterate and remove
        dirty_list = list(_DIRTY)
        take = set(dirty_list[:batch_size])
        _DIRTY.difference_update(take)
        return take


async def _flush_batch(arm_ids: set[str]) -> None:
    if not arm_ids:
        return

    payload = []
    for aid in arm_ids:
        arm: PolicyArm | None = arm_registry.get_arm(aid)
        if arm is None:
            continue

        state = arm.bandit_head.get_state()
        payload.append({"id": arm.id, **state})

    if not payload:
        return

    # This Cypher query atomically updates the state properties of the matched PolicyArm nodes.
    q = """
    UNWIND $rows AS row
    MATCH (p:PolicyArm {id: row.id})
    SET p.A = row.A,
        p.A_shape = row.A_shape,
        p.b = row.b,
        p.b_shape = row.b_shape,
        p.updated_at = datetime()
    """
    await cypher_query(q, {"rows": payload})
    logger.info(f"[BanditState] Flushed state for {len(payload)} arms to graph.")


async def flush_now(batch_size: int = 128) -> None:
    """Public API to flush all dirty arms now (useful in tests or shutdown)."""
    while True:
        arm_ids = _drain_dirty(batch_size)
        if not arm_ids:
            break
        await _flush_batch(arm_ids)


# --- CHANGED: This function is now a thread-safe scheduler ---
def start_background_flusher(
    loop: asyncio.AbstractEventLoop, interval_sec: float = 30.0, batch_size: int = 128
) -> None:
    """Starts the background snapshotter task in a thread-safe way."""
    global _flush_task
    if _flush_task and not _flush_task.done():
        return

    async def _flusher_loop():
        """The background task that periodically flushes dirty state."""
        try:
            while True:
                await asyncio.sleep(interval_sec)
                arm_ids = _drain_dirty(batch_size)
                if not arm_ids:
                    continue
                await _flush_batch(arm_ids)
        except asyncio.CancelledError:
            logger.info("[BanditState] Flusher cancelled. Performing final flush...")
            await flush_now(batch_size=batch_size)
            # Do not re-raise CancelledError here, just let the task end.

    # This is the key change: we use the loop that was passed in from the main thread.
    # We use call_soon_threadsafe because this function is being run from a separate thread.
    def _schedule_task():
        global _flush_task
        if not loop.is_closed():
            _flush_task = loop.create_task(_flusher_loop())
            logger.info(f"[BanditState] Background flusher started with {interval_sec}s interval.")

    loop.call_soon_threadsafe(_schedule_task)


def stop_background_flusher() -> None:
    """Cancels the background snapshotter and flushes remaining updates."""
    global _flush_task
    if _flush_task and not _flush_task.done():
        # This needs to be thread-safe as well
        loop = _flush_task.get_loop()
        loop.call_soon_threadsafe(_flush_task.cancel)
