# systems/synapse/training/adversary.py
# --- CORRECTED & ALIGNED ---
from __future__ import annotations

import random
from typing import Any

# FIX: Import the canonical, modern SynapseClient from the core services layer.
from core.services.synapse import SynapseClient
from systems.synapse.schemas import Candidate, TaskContext
from systems.synk.core.switchboard.gatekit import gated_loop


class AdversarialAgent:
    """
    A co-evolving "Red Team Agent" that learns to generate challenging tasks
    to find flaws in Synapse's policies (H14).
    """

    _instance: AdversarialAgent | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls.task_values: dict[str, float] = {
                "code_repair_deep_recursion": 0.0,
                "multi_agent_tool_synthesis": 0.0,
                "data_analysis_with_corrupted_input": 0.0,
                "resource_planning_under_constraint_shift": 0.0,
            }
            cls.learning_rate = 0.1
            cls.exploration_rate = 0.2
        return cls._instance

    def _generate_challenging_task_context(self) -> TaskContext:
        """Generates a task context designed to probe for system weaknesses."""
        tasks = list(self.task_values.keys())
        chosen_task = (
            random.choice(tasks)
            if random.random() < self.exploration_rate
            else max(self.task_values, key=self.task_values.get)
        )

        return TaskContext(
            task_key=chosen_task,
            goal=f"Adversarial challenge: Execute {chosen_task} under difficult conditions.",
            risk_level=random.choice(["low", "medium", "high"]),
            budget=random.choice(["constrained", "normal", "extended"]),
        )

    def _update_task_values(self, task_key: str, synapse_reward: float):
        """The adversary's reward is the inverse of Synapse's reward."""
        adversary_reward = -synapse_reward
        old_value = self.task_values.get(task_key, 0.0)
        new_value = old_value + self.learning_rate * (adversary_reward - old_value)
        self.task_values[task_key] = new_value
        print(f"[Adversary] Task '{task_key}' value updated to {new_value:.3f}")

    async def run_adversarial_cycle(self):
        """
        Executes one cycle of generating a task, submitting it to Synapse,
        simulating an outcome, and learning from it.
        """
        print("\n" + "=" * 20 + " ADVERSARIAL CYCLE START " + "=" * 20)
        task_ctx = self._generate_challenging_task_context()
        client = SynapseClient()

        try:
            # FIX: Use the correct select_or_plan method.
            selection = await client.select_or_plan(task_ctx, candidates=[])

            simulated_success = random.random() > (
                0.5 - self.task_values.get(task_ctx.task_key, 0.0)
            )
            simulated_reward = 1.0 if simulated_success else -1.0

            # The log_outcome call is now correct, with the arm_id inside the metrics.
            await client.log_outcome(
                episode_id=selection.episode_id,
                task_key=task_ctx.task_key,
                metrics={
                    "chosen_arm_id": selection.champion_arm.arm_id,
                    "simulated": True,
                    "success": simulated_success,
                    "cost_units": 5.0,
                },
            )

            self._update_task_values(task_ctx.task_key, simulated_reward)
        except Exception as e:
            print(f"[Adversary] ERROR during adversarial cycle: {e}")
        finally:
            print("=" * 22 + " ADVERSARIAL CYCLE END " + "=" * 23 + "\n")


async def start_adversary_loop():
    """Daemon function to run the Adversarial Agent periodically."""
    adversary = AdversarialAgent()
    await gated_loop(
        task_coro=adversary.run_adversarial_cycle,
        enabled_key="synapse.adversary.enabled",
        interval_key="synapse.adversary.interval_sec",
        default_interval=300,
    )
