# systems/synapse/core/snapshots.py
# FINAL PRODUCTION VERSION
import os
from typing import Any


def get_component_version(component_name: str) -> str:
    """
    Returns a stable version for a system component, read from environment
    variables set during a CI/CD deployment.
    """
    # Maps internal component names to expected environment variables.
    env_var_map = {
        "rules_version": "EQUOR_RULES_VERSION",
        "encoder_hash": "SYNAPSE_ENCODER_VERSION",
        "critic_version": "SYNAPSE_CRITIC_VERSION",
        "simulator_version": "SYNAPSE_WORLD_MODEL_VERSION",
    }
    env_var = env_var_map.get(component_name)
    # Return the version from the environment, or a default if not set.
    return os.getenv(env_var, f"unknown-{component_name}-version")


def stamp() -> dict[str, Any]:
    """
    Generates a complete RCU snapshot for a decision, capturing the versions
    of all components involved.
    """
    snapshot = {
        "rules_version": get_component_version("rules_version"),
        "encoder_hash": get_component_version("encoder_hash"),
        "critic_version": get_component_version("critic_version"),
        "simulator_version": get_component_version("simulator_version"),
    }
    print(f"[Snapshots] Generated RCU stamp: {snapshot}")
    return snapshot
