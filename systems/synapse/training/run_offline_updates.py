# systems/synapse/training/run_offline_updates.py
# FINAL VERSION - CLEANED UP AND MODULAR

from __future__ import annotations

import asyncio

# Core Synapse Learning Modules
from systems.synapse.critic.offpolicy import critic
from systems.synapse.meta.optimizer import meta_optimizer
from systems.synapse.qd.replicator import replicator
from systems.synapse.training.attention_trainer import attention_trainer

# --- L-SERIES UPGRADE: Import the new DEDICATED trainers ---
from systems.synapse.training.self_model_trainer import self_model_trainer
from systems.synapse.training.tom_trainer import tom_trainer
from systems.synapse.values.learner import value_learner
from systems.synapse.world.world_model_trainer import world_model_trainer


async def run_full_offline_pipeline():
    """
    Orchestrates the entire offline learning, optimization, and maturation
    pipeline for Synapse. This is the heart of autonomous self-improvement.
    """
    print("\n" + "=" * 25 + " SYNAPSE OFFLINE PIPELINE START " + "=" * 25)

    # 1. Train Core Predictive Models on the latest data.
    print("\n--- Step 1: Training Core Predictive Models ---")
    await asyncio.gather(critic.fit_nightly(), world_model_trainer.train_and_save_model())

    # 2. Train L-Series Cognitive Architecture Models
    print("\n--- Step 2: Training L-Series Cognitive Architecture Models ---")
    await asyncio.gather(
        self_model_trainer.train_cycle(),
        tom_trainer.train_cycle(),
        attention_trainer.train_cycle(),
    )

    # 3. Align System Values from human preferences.
    print("\n--- Step 3: Aligning Values via Preference Learning ---")
    await value_learner.run_learning_cycle()

    # 4. Run self-referential optimization to find better hyperparameters.
    print("\n--- Step 4: Meta-Optimizing Hyperparameters ---")
    await meta_optimizer.run_optimization_cycle()

    # 5. Rebalance the exploration strategy based on latest performance.
    print("\n--- Step 5: Rebalancing Exploration Strategy using Replicator Dynamics ---")
    replicator.rebalance_shares()

    print("\n" + "=" * 26 + " SYNAPSE OFFLINE PIPELINE END " + "=" * 27 + "\n")


if __name__ == "__main__":
    asyncio.run(run_full_offline_pipeline())
