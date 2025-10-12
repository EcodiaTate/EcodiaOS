# core/utils/neo/initial_data.py
from __future__ import annotations

import json
import logging

from core.utils.neo.cypher_query import cypher_query
from systems.simula.agent.tool_names import CANONICAL_TOOL_NAMES
from systems.synapse.policy.policy_dsl import PolicyGraph, PolicyNode

logger = logging.getLogger(__name__)
SIMULA_AGENT_NAME = "Simula"


def create_seed_policy_graph(name: str) -> dict:
    """Creates a safe, default policy graph."""
    graph = PolicyGraph(
        version=1,
        id=f"pg::{name}",
        nodes=[
            PolicyNode(
                id="prompt", type="prompt", model="gpt-3.5-turbo", params={"temperature": 0.15}
            )
        ],
        edges=[],
        meta={"seeded": True, "arm": name},
    )
    return graph.model_dump(mode="json")
