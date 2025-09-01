# systems/synapse/core/registry_bootstrap.py
from __future__ import annotations

import json
from typing import Iterable

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry import ArmRegistry
# Import Simula’s canonical tool names (this is the source of truth)
from systems.simula.agent.tool_registry import TOOLS as SIMULA_TOOLS  # keys are tool names

def _noop_pg_dict(arm_id: str) -> dict:
    # SAFE prompt-only graph; zero side-effects; firewall will treat as safe fallback
    return {
        "version": 1,
        "nodes": [
            {
                "id": "n_prompt",
                "type": "prompt",
                "prompt": f"Policy arm '{arm_id}' — safe prompt node (no effects).",
                "temperature": 0.1,
            }
        ],
        "edges": [],
        "constraints": [],
        "meta": {"kind": "seed", "safe": True},
    }

async def _persist_arms(tool_names: Iterable[str]) -> None:
    # Persist PolicyArm nodes so ArmRegistry can hydrate them at init
    await cypher_query(
        """
        UNWIND $names AS name
        MERGE (a:PolicyArm {id: name})
        ON CREATE SET
          a.mode = 'planful',
          a.policy_graph = $pg_json,
          a.created_at = datetime()
        """,
        {
            "names": list(tool_names),
            "pg_json": json.dumps(_noop_pg_dict("__seed__")),  # same SAFE PG for all, OK
        },
    )

def ensure_minimum_arms(registry: ArmRegistry) -> None:
    """
    Called by ArmRegistry.ensure_cold_start() if available.
    Seeds the graph with arms whose IDs exactly equal Simula's tool names.
    Also seeds in-memory registry with the same IDs so selection can proceed immediately.
    """
    tool_names = list(SIMULA_TOOLS.keys())
    # Persist to graph (ignore errors in best-effort seeders)
    try:
        import asyncio
        asyncio.get_event_loop().run_until_complete(_persist_arms(tool_names))
    except Exception:
        pass

    # Add to in-memory registry (SAFE graphs; selection id == tool name)
    for name in tool_names:
        try:
            registry.add_arm(
                arm_id=name,
                policy_graph=_noop_pg_dict(name),
                mode="planful",
                meta={"kind": "seed", "source": "registry_bootstrap"},
            )
        except Exception:
            continue
