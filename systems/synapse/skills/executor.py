# systems/synapse/skills/executor.py
# NEW FILE
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from systems.synapse.core.registry import arm_registry
from systems.synapse.schemas import PolicyArmModel as PolicyArm
from systems.synapse.skills.schemas import Option


@dataclass
class ExecutionState:
    """Tracks the progress of a single long-horizon skill execution."""

    episode_id: str
    option: Option
    current_step: int = 0
    step_outcomes: dict[int, Any] = field(default_factory=dict)


# This will store the state of all ongoing multi-step executions.
# In production, this would be backed by a fast k-v store like Redis.
_ACTIVE_EXECUTIONS: dict[str, ExecutionState] = {}
_LOCK = threading.RLock()


class OptionExecutor:
    """
    A stateful service to manage the step-by-step execution of hierarchical Options.
    """

    def start_execution(self, episode_id: str, option: Option) -> PolicyArm | None:
        """Initiates a new skill execution and returns the first arm."""
        with _LOCK:
            if episode_id in _ACTIVE_EXECUTIONS:
                return None  # Already running

            state = ExecutionState(episode_id=episode_id, option=option)
            _ACTIVE_EXECUTIONS[episode_id] = state

            first_arm_id = option.policy_sequence[0]
            print(
                f"[Executor] Starting execution of Option '{option.id}' for episode '{episode_id}'.",
            )
            return arm_registry.get_arm(first_arm_id)

    def continue_execution(self, episode_id: str, last_step_outcome: Any) -> PolicyArm | None:
        """
        Logs the outcome of the previous step and returns the next arm in the sequence.
        Returns None if the skill is complete or has failed.
        """
        with _LOCK:
            state = _ACTIVE_EXECUTIONS.get(episode_id)
            if not state:
                return None  # No active execution found

            # Log outcome and advance the step counter
            state.step_outcomes[state.current_step] = last_step_outcome
            state.current_step += 1

            # Check for completion
            if state.current_step >= len(state.option.policy_sequence):
                print(
                    f"[Executor] Option '{state.option.id}' completed successfully for episode '{episode_id}'.",
                )
                del _ACTIVE_EXECUTIONS[episode_id]
                return None  # Signal completion

            # Get the next arm
            next_arm_id = state.option.policy_sequence[state.current_step]
            print(
                f"[Executor] Continuing Option '{state.option.id}' to step {state.current_step + 1}: Arm '{next_arm_id}'.",
            )
            return arm_registry.get_arm(next_arm_id)

    def end_execution(self, episode_id: str):
        """Forcefully ends an execution, e.g., on failure."""
        with _LOCK:
            if episode_id in _ACTIVE_EXECUTIONS:
                del _ACTIVE_EXECUTIONS[episode_id]
                print(f"[Executor] Execution for episode '{episode_id}' has been terminated.")


# Singleton export
option_executor = OptionExecutor()
