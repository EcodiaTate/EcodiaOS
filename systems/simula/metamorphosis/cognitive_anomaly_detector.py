# --- DRIVER-AWARE LISTENER; PRESERVES COMMENTED SELF-MOD FUNCTION ---
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict, deque
from typing import Deque, Dict

import redis.asyncio as redis

from core.utils.neo.neo_driver import close_driver, init_driver  # Initialize like other daemons

# from systems.simula.nscs.agent_tools import initiate_self_modification

log = logging.getLogger(__name__)

# Configuration for the Anomaly Detector
EVENT_STREAM_KEY = os.getenv("MDO_EVENT_STREAM_KEY", "mdo:event_stream")
MAX_EVENT_HISTORY = int(os.getenv("MDO_MAX_EVENT_HISTORY", "100"))
ANOMALY_PATTERNS = {
    "REPEATED_PLAN_REJECTION": {
        "threshold": int(
            os.getenv("MDO_PLAN_REJECTION_THRESHOLD", "3"),
        ),  # 3 rejections for the same reason
        "meta_goal_template": (
            "My deliberation process is consistently failing to produce an approved plan for tasks "
            "involving '{target_fqname}'. The rejection reason is '{reason}'. Analyze the deliberation logic in "
            "`systems/simula/agent/deliberation.py` and improve the Planner or Judge prompts to prevent this recurring failure."
        ),
    },
    "REPEATED_TOOL_CRASH": {
        "threshold": int(os.getenv("MDO_TOOL_CRASH_THRESHOLD", "3")),
        "meta_goal_template": (
            "The tool '{tool_name}' has crashed {threshold} times with the error: '{reason}'. "
            "Analyze the tool's implementation in `systems/simula/nscs/agent_tools.py` and add the necessary error "
            "handling or logic corrections to make it more robust."
        ),
    },
}


class CognitiveAnomalyDetector:
    """
    The MDO's Cerebral Cortex. It monitors the agent's performance, detects
    systemic weaknesses, and triggers the self-modification (Crucible) process
    to evolve the agent's own source code.
    """

    def __init__(self):
        self.event_history: deque[dict] = deque(maxlen=MAX_EVENT_HISTORY)
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.running = False
        self.repo_url = os.getenv(
            "GIT_REPO_URL",
            "https://github.com/YourOrg/EcodiaOS.git",
        )  # IMPORTANT: Configure this env var

    async def _listen_for_events(self):
        """Listens to a Redis stream for events published by the Orchestrator."""
        log.info("[Cortex] Listening for MDO events on Redis stream '%s'...", EVENT_STREAM_KEY)

        # Start at the end-of-stream so we only get new events
        last_id = "$"

        while self.running:
            try:
                # Blocking read; returns as soon as there's at least one new message
                # Note: count=1 keeps wakeups frequent; tune if you want batch processing
                events = await self.redis_client.xread(
                    {EVENT_STREAM_KEY: last_id},
                    block=0,
                    count=1,
                )
                for stream, messages in events:
                    for message_id, event_data in messages:
                        last_id = message_id  # advance the cursor
                        log.info("[Cortex] Received event: %s", event_data.get("event_type"))
                        self.event_history.append(event_data)
                        await self._analyze_for_anomalies()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("[Cortex] Error in event listener: %r", e, exc_info=True)
                # Backoff to avoid hot-looping on errors
                await asyncio.sleep(10)

    async def _analyze_for_anomalies(self):
        """Analyzes the recent event history to detect systemic failures."""
        # --- Detect Repeated Plan Rejection ---
        rejection_reasons = defaultdict(int)
        last_rejection_event = None
        for event in self.event_history:
            if event.get("event_type") == "plan_rejected":
                reason = event.get("reason", "Unknown Reason")
                rejection_reasons[reason] += 1
                last_rejection_event = event

        for reason, count in rejection_reasons.items():
            pattern = ANOMALY_PATTERNS["REPEATED_PLAN_REJECTION"]
            if count >= pattern["threshold"]:
                log.warning(
                    "[Cortex] Anomaly Detected: Repeated Plan Rejection (Reason: %s)",
                    reason,
                )
                meta_goal = pattern["meta_goal_template"].format(
                    target_fqname=(last_rejection_event or {}).get("target_fqname", "N/A"),
                    reason=reason,
                )
                await self._trigger_self_modification(meta_goal)
                self.event_history.clear()  # Clear history to prevent re-triggering
                return

        # --- Detect Repeated Tool Crash ---
        tool_crashes = defaultdict(int)
        last_crash_event = None
        for event in self.event_history:
            if event.get("event_type") == "tool_crashed":
                tool_name = event.get("tool_name", "Unknown Tool")
                tool_crashes[tool_name] += 1
                last_crash_event = event

        for tool_name, count in tool_crashes.items():
            pattern = ANOMALY_PATTERNS["REPEATED_TOOL_CRASH"]
            if count >= pattern["threshold"]:
                log.warning("[Cortex] Anomaly Detected: Repeated Tool Crash (Tool: %s)", tool_name)
                meta_goal = pattern["meta_goal_template"].format(
                    tool_name=tool_name,
                    threshold=count,
                    reason=(last_crash_event or {}).get("reason", "N/A"),
                )
                # Keep this disabled unless you're ready for Crucible to start changing code.
                # await self._trigger_self_modification(meta_goal)
                self.event_history.clear()
                return

    # --- keep this commented block as requested ---
    # async def _trigger_self_modification(self, meta_goal: str):
    #     """Initiates the Crucible process in a fire-and-forget manner."""
    #     log.info(f"[Cortex] Triggering self-modification with meta-goal: '{meta_goal}'")
    #     # We don't await this; the Crucible is a long-running, autonomous process.
    #     asyncio.create_task(
    #         initiate_self_modification(
    #             meta_goal=meta_goal,
    #             repo_url=self.repo_url
    #         )
    #     )

    async def _trigger_self_modification(self, meta_goal: str):
        """No-op placeholder while Crucible is disabled; preserves call sites."""
        log.info("[Cortex] (noop) Would trigger self-modification with meta-goal: %s", meta_goal)

    async def start(self):
        """Starts the Cortex's main loop."""
        self.running = True
        await self._listen_for_events()

    def stop(self):
        self.running = False
        log.info("[Cortex] Shutting down.")


# -------- Process entrypoints (driver-aware, for consistency) --------


async def main():
    # Even if Cortex doesn't currently query Neo4j, we init the driver
    # so adding cypher calls later won't crash with "driver not initialized".
    try:
        await init_driver()
        log.info("[Cortex] ✅ Neo4j driver initialized.")
    except Exception as e:
        log.error("[Cortex] ❌ Failed to init Neo4j driver: %r", e)
        # Cortex can still run without Neo4j; continue.
    try:
        detector = CognitiveAnomalyDetector()
        await detector.start()
    finally:
        # Only attempt to close if it was opened; close_driver() is safe to call.
        await close_driver()
        log.info("[Cortex] Closed Neo4j driver (if open).")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("[Cortex] Shutting down.")
