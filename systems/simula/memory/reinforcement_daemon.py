# --- DRIVER-AWARE, ROBUST VERSION ---
from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict, List

from core.services.synapse import SynapseClient
from core.utils.neo.cypher_query import cypher_query
from core.utils.neo.neo_driver import close_driver, init_driver

log = logging.getLogger(__name__)

DEFAULT_POLL_SEC = 300  # 5 minutes


class ReinforcementDaemon:
    """
    A background service that closes the MDO's learning loop.
    It periodically syncs reflex performance scores from Synapse
    back to the SynapticTrace nodes in the Neo4j graph, adjusting
    their confidence scores so the MDO learns which reflexes to trust.
    """

    def __init__(self, poll_interval_seconds: int | None = None):
        self.synapse = SynapseClient()
        self.poll_interval = poll_interval_seconds or int(
            os.getenv("MDO_REINFORCEMENT_POLL_SEC", DEFAULT_POLL_SEC)
        )
        self.running = False

    async def _get_all_trace_ids(self) -> list[str]:
        """Fetches all trace_ids from the graph."""
        query = "MATCH (t:SynapticTrace) RETURN t.trace_id AS traceId"
        results = await cypher_query(query)
        return [r.get("traceId") for r in results if r.get("traceId")]

    async def _update_confidence_scores(self, scores: dict[str, float]):
        """Updates the confidence_score for multiple traces in a single transaction."""
        if not scores:
            return

        query = """
        UNWIND $scores AS score_update
        MATCH (t:SynapticTrace {trace_id: score_update.trace_id})
        SET t.confidence_score = score_update.new_score
        """
        params = [{"trace_id": tid, "new_score": score} for tid, score in scores.items()]
        await cypher_query(query, {"scores": params})
        log.info("[ReinforcementDaemon] Updated confidence scores for %d traces.", len(scores))

    async def run_once(self):
        """Performs a single cycle of fetching and updating scores."""
        log.info("[ReinforcementDaemon] Starting reinforcement cycle...")
        try:
            trace_ids = await self._get_all_trace_ids()
            if not trace_ids:
                log.info("[ReinforcementDaemon] No traces found in graph. Cycle complete.")
                return

            # The arm_id in Synapse is prefixed, e.g., "trace::trace_xyz"
            arm_ids_for_synapse = [f"trace::{tid}" for tid in trace_ids]

            # Fetch the latest scores from the bandit policy engine
            arm_scores = await self.synapse.get_arm_scores(arm_ids_for_synapse)

            scores_to_update: dict[str, float] = {}
            for arm in arm_scores:
                # Strip the prefix to get the trace_id
                trace_id = (arm.arm_id or "").split("::")[-1]
                # Normalize score into [0,1]
                new_confidence = max(0.0, min(1.0, float(arm.score or 0.0)))
                if trace_id:
                    scores_to_update[trace_id] = new_confidence

            if scores_to_update:
                await self._update_confidence_scores(scores_to_update)

            log.info("[ReinforcementDaemon] Reinforcement cycle finished successfully.")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("[ReinforcementDaemon] Cycle failed: %r", e, exc_info=True)

    async def start(self):
        """Starts the daemon's continuous polling loop."""
        self.running = True
        log.info("[ReinforcementDaemon] Starting with poll interval=%ds.", self.poll_interval)
        try:
            while self.running:
                await self.run_once()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            log.info("[ReinforcementDaemon] Exiting loop.")

    def stop(self):
        """Stops the daemon."""
        self.running = False


# -------- Process entrypoints (driver-aware) --------


async def main():
    # Ensure Neo4j driver is initialized for this separate process
    try:
        await init_driver()
        log.info("[ReinforcementDaemon] ✅ Neo4j driver initialized.")
    except Exception as e:
        log.error("[ReinforcementDaemon] ❌ Failed to init Neo4j driver: %r", e)
        return

    daemon = ReinforcementDaemon()
    try:
        await daemon.start()
    finally:
        await close_driver()
        log.info("[ReinforcementDaemon] Closed Neo4j driver.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("[ReinforcementDaemon] Shutting down.")
