# --- FIXED, STABLE VERSION ---
from __future__ import annotations

import asyncio
import logging
import os

# --- Core Services ---
from core.utils.neo.neo_driver import close_driver, init_driver
from systems.synapse.safety.sentinels import goodhart_sentinel
from systems.synapse.skills.options import option_miner
from systems.synapse.training.adversary import start_adversary_loop
from systems.synapse.training.hall_of_fame_promoter import hall_of_fame_promoter

# --- Advanced Self-Tuning and Adversarial Modules ---
from systems.synapse.training.meta_controller import start_meta_controller_loop

# --- Core Autonomous Learning & Evolution Modules ---
from systems.synapse.training.run_offline_updates import run_full_offline_pipeline
from systems.synk.core.switchboard.gatekit import gated_loop

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# Optional development flag to skip heavy background tasks
# ---------------------------------------------------------------------------
DEV_MODE = os.getenv("DEV_FOCUS_MODE", "").lower()
DISABLE_BACKGROUND_LOOPS = os.getenv("DISABLE_BACKGROUND_LOOPS", "0").lower() in (
    "1",
    "true",
    "yes",
)
RUN_ONCE_FOR_DEBUG = os.getenv("RUN_ONCE_FOR_DEBUG", "0").lower() in ("1", "true")


# ---------------------------------------------------------------------------
# Safe, driver-aware startup
# ---------------------------------------------------------------------------


async def run_synapse_autonomous_loops():
    """
    The main entry point for all of Synapse's background, autonomous processes.
    Initializes the Neo4j driver once, then orchestrates all learning/evolution loops.
    """
    logger.info("[Synapse Daemon] Starting all autonomous background loops...")

    # --- Ensure Neo4j driver is ready ---
    try:
        await init_driver()
        logger.info("[Synapse Daemon] ✅ Neo4j driver initialized.")
    except Exception as e:
        logger.error("[Synapse Daemon] ❌ Failed to init Neo4j driver: %r", e)
        return

    # --- Short-circuit for development or one-off tests ---
    if DISABLE_BACKGROUND_LOOPS:
        logger.warning("[Synapse Daemon] Background loops disabled (DISABLE_BACKGROUND_LOOPS=1).")
        await asyncio.sleep(9999999)  # keep container alive doing nothing
        return

    # In dev mode, you might only want meta‑controller tuning or lightweight loops.
    if DEV_MODE:
        logger.warning(f"[Synapse Daemon] DEV_FOCUS_MODE active: {DEV_MODE!r}")
        if DEV_MODE.startswith("simula"):
            # Just meta controller + minimal background safety checks
            await asyncio.gather(
                gated_loop(
                    task_coro=start_meta_controller_loop,
                    enabled_key="synapse.meta_tuning.enabled",
                    interval_key="synapse.meta_tuning.interval_sec",
                    default_interval=600,
                ),
                gated_loop(
                    task_coro=goodhart_sentinel.fit,
                    enabled_key="synapse.sentinel_training.enabled",
                    interval_key="synapse.sentinel_training.interval_sec",
                    default_interval=1800,
                ),
            )
            return

    # --- Full autonomous operation ---
    try:
        await asyncio.gather(
            # Offline pipeline: critics, world model, etc.
            gated_loop(
                task_coro=run_full_offline_pipeline,
                enabled_key="synapse.offline_learning.enabled",
                interval_key="synapse.offline_learning.interval_sec",
                default_interval=86400,  # daily
                run_once=RUN_ONCE_FOR_DEBUG,
            ),
            # Option mining
            gated_loop(
                task_coro=option_miner.mine_and_save_options,
                enabled_key="synapse.option_mining.enabled",
                interval_key="synapse.option_mining.interval_sec",
                default_interval=43200,  # twice per day
                run_once=RUN_ONCE_FOR_DEBUG,
            ),
            # Hall of Fame promotion
            gated_loop(
                task_coro=hall_of_fame_promoter.run_promotion_cycle,
                enabled_key="synapse.hof_promotion.enabled",
                interval_key="synapse.hof_promotion.interval_sec",
                default_interval=86400,
                run_once=RUN_ONCE_FOR_DEBUG,
            ),
            # Safety sentinel retraining
            gated_loop(
                task_coro=goodhart_sentinel.fit,
                enabled_key="synapse.sentinel_training.enabled",
                interval_key="synapse.sentinel_training.interval_sec",
                default_interval=21600,
                run_once=RUN_ONCE_FOR_DEBUG,
            ),
            # Meta controller tuning
            gated_loop(
                task_coro=start_meta_controller_loop,
                enabled_key="synapse.meta_tuning.enabled",
                interval_key="synapse.meta_tuning.interval_sec",
                default_interval=900,
                run_once=RUN_ONCE_FOR_DEBUG,
            ),
            # Adversarial "red team"
            gated_loop(
                task_coro=start_adversary_loop,
                enabled_key="synapse.adversary.enabled",
                interval_key="synapse.adversary.interval_sec",
                default_interval=300,
                run_once=RUN_ONCE_FOR_DEBUG,
            ),
        )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception("[Synapse Daemon] Unexpected error in background loops: %r", e)
    finally:
        await close_driver()
        logger.info("[Synapse Daemon] Closed Neo4j driver and shutting down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(run_synapse_autonomous_loops())
    except KeyboardInterrupt:
        logger.info("[Synapse Daemon] Shutting down.")
