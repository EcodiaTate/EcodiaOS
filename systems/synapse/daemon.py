# systems/synapse/daemon.py
import asyncio

# Import all the autonomous modules we've built
from systems.synapse.core.arm_genesis import genesis_scan_and_mint
from systems.synapse.safety.sentinels import goodhart_sentinel
from systems.synapse.skills.options import option_miner
from systems.synapse.training.run_offline_updates import run_full_offline_pipeline
from systems.synk.core.switchboard.gatekit import gated_loop


async def run_synapse_autonomous_loops():
    """
    The main entry point for all of Synapse's background, autonomous processes.
    This function orchestrates the learning, evolution, and safety monitoring loops.
    """
    print("[Synapse Daemon] Starting all autonomous background loops...")

    # Each process is wrapped in `gated_loop` which allows us to enable/disable
    # and configure its run interval from a central configuration system.

    await asyncio.gather(
        # The core evolutionary loop that creates new policy arms.
        gated_loop(
            task_coro=genesis_scan_and_mint,
            enabled_key="synapse.genesis.enabled",
            interval_key="synapse.genesis.interval_sec",
            default_interval=3600,  # Runs every hour
        ),
        # The full offline pipeline for learning from past experience.
        gated_loop(
            task_coro=run_full_offline_pipeline,
            enabled_key="synapse.offline_learning.enabled",
            interval_key="synapse.offline_learning.interval_sec",
            default_interval=86400,  # Runs once a day
        ),
        # The loop for fitting the anomaly detection model for the sentinel.
        gated_loop(
            task_coro=goodhart_sentinel.fit,
            enabled_key="synapse.sentinel_training.enabled",
            interval_key="synapse.sentinel_training.interval_sec",
            default_interval=21600,  # Re-trains every 6 hours
        ),
        # The loop for discovering new hierarchical skills.
        gated_loop(
            task_coro=option_miner.mine_and_save_options,
            enabled_key="synapse.option_mining.enabled",
            interval_key="synapse.option_mining.interval_sec",
            default_interval=43200,  # Mines for new skills twice a day
        ),
    )


if __name__ == "__main__":
    # This allows the daemon to be started as a standalone process.
    try:
        asyncio.run(run_synapse_autonomous_loops())
    except KeyboardInterrupt:
        print("[Synapse Daemon] Shutting down.")
