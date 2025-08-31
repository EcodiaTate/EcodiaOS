# systems/synapse/core/arm_genesis.py
# FINAL, COMPLETE VERSION
from __future__ import annotations

import uuid

import numpy as np

from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.synapse.core.registry import arm_registry
from systems.synapse.economics.roi import roi_manager
from systems.synapse.policy.policy_dsl import PolicyGraph
from systems.synapse.qd.map_elites import qd_archive
from systems.synapse.qd.replicator import replicator

GENESIS_MIN_EPISODES = 20
GENESIS_FAILURE_RATIO = 0.35
TOTAL_GENESIS_BUDGET = 20  # Total new arms to create per cycle


def _generate_base_graph(task: str) -> PolicyGraph:
    return PolicyGraph.model_validate(
        {
            "version": 1,
            "nodes": [
                {
                    "id": "prompt_main",
                    "type": "prompt",
                    "model": "gpt-4o",
                    "params": {"temperature": 0.5},
                    "effects": ["read"],
                },
            ],
            "edges": [],
            "constraints": [],
        },
    )


def _mutations(base_graph: PolicyGraph, count: int) -> list[PolicyGraph]:
    if count == 0:
        return []
    candidates = []
    # Simplified mutation strategy for demonstration
    for i in range(count):
        mutated_graph = base_graph.copy(deep=True)
        for node in mutated_graph.nodes:
            if node.type == "prompt":
                # Add jitter to temperature
                node.params["temperature"] = max(
                    0.1,
                    min(
                        1.5,
                        base_graph.nodes[0].params.get("temperature", 0.7)
                        + (np.random.randn() * 0.2),
                    ),
                )
        candidates.append(mutated_graph)
    return candidates


async def _registry_reload() -> None:
    client = await get_http_client()
    r = await client.post(ENDPOINTS.SYNAPSE_REGISTRY_RELOAD)
    r.raise_for_status()


async def _prune_underperformers():
    to_prune = roi_manager.get_underperforming_arms(percentile_threshold=10)
    if not to_prune:
        return 0
    print(f"[ArmGenesis] Pruning {len(to_prune)} underperforming arms...")
    query = "MATCH (p:PolicyArm) WHERE p.id IN $ids DETACH DELETE p"
    await cypher_query(query, {"ids": to_prune})
    return len(to_prune)


async def genesis_scan_and_mint() -> None:
    """
    The full evolutionary loop, now with strategically budgeted exploration.
    """
    pruned_count = await _prune_underperformers()
    if pruned_count > 0:
        await _registry_reload()

    # Always rebalance shares based on the latest performance data
    replicator.rebalance_shares()
    minted = 0

    # Get the strategic allocation of our evolutionary budget from the Replicator
    allocations = replicator.get_genesis_allocation(TOTAL_GENESIS_BUDGET)

    for niche, count in allocations.items():
        if count == 0:
            continue

        print(
            f"[ArmGenesis] Allocating {count} mutations to niche {niche} based on replicator dynamics.",
        )
        parent_graph = None
        champion_id = qd_archive.get_champion_from_niche(niche)
        if champion_id:
            parent_arm = arm_registry.get_arm(champion_id)
            if parent_arm:
                parent_graph = parent_arm.policy_graph

        base_graph = parent_graph or _generate_base_graph(str(niche))
        # Generate the budgeted number of mutations for this niche
        candidate_graphs = _mutations(base_graph, count)
        minted += await _mint_graphs(candidate_graphs, mode="qd_driven", task="_".join(niche))

    if minted > 0:
        print(
            f"[ArmGenesis] Minted a total of {minted} new PolicyGraph arms based on strategic budget.",
        )
        await _registry_reload()


async def _mint_graphs(graphs: list[PolicyGraph], mode: str, task: str) -> int:
    if not graphs:
        return 0
    arms_payload = []
    for graph in graphs:
        arm_id = f"{task.lower()}_{mode.lower()}_gen_{uuid.uuid4().hex[:8]}"
        arms_payload.append(
            {
                "id": arm_id,
                "mode": mode,
                "policy_graph_json": graph.model_dump_json(sort_keys=True, exclude_none=True),
                "canonical_hash": graph.canonical_hash,
            },
        )
    create_q = """
    UNWIND $arms AS a
    MERGE (p:PolicyArm {canonical_hash: a.canonical_hash})
    ON CREATE SET p.id = a.id, p.arm_id = a.id, p.mode = a.mode, p.policy_graph = a.policy_graph_json,
                  p.created_at = datetime(), p.updated_at = datetime()
    """
    await cypher_query(create_q, {"arms": arms_payload})
    return len(arms_payload)
