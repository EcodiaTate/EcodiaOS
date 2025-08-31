# systems/synapse/skills/options.py
# CORRECTED VERSION
from __future__ import annotations

from uuid import uuid4

import numpy as np

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.skills.schemas import Option


class OptionMiner:
    """
    Mines historical episode data to discover reusable, high-performing
    sequences of actions (Options) for hierarchical planning. (H13)
    """

    _instance: OptionMiner | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _fetch_successful_chains(self, min_length: int = 3, limit: int = 100) -> list[dict]:
        """Fetches chains of high-reward, consecutive episodes from the graph."""
        query = """
        MATCH path = (e_start:Episode)-[:PRECEDES*..5]->(e_end:Episode)
        WHERE e_start.task_key = e_end.task_key
          AND e_end.reward > 0.8
          AND length(path) >= $min_length
        WITH
          [n IN nodes(path) | {id: n.id, arm: n.chosen_arm_id, ctx: n.x_context}] AS nodes,
          e_end.reward AS final_reward
        RETURN nodes, final_reward
        ORDER BY final_reward DESC
        LIMIT $limit
        """
        return await cypher_query(query, {"min_length": min_length, "limit": limit}) or []

    async def mine_and_save_options(self):
        """
        The main orchestration method. Fetches successful chains, identifies
        common patterns (options), and saves them to the graph.
        """
        print("[OptionMiner] Starting mining cycle for hierarchical skills...")
        chains = await self._fetch_successful_chains()
        if not chains:
            print("[OptionMiner] No new successful chains found to analyze.")
            return

        new_options_payload = []  # <-- FIX: Variable defined here
        for chain_data in chains:
            nodes = chain_data.get("nodes", [])
            if not nodes:
                continue

            start_context_vec = np.array(nodes[0]["ctx"])
            policy_sequence = [node["arm"] for node in nodes]

            option = Option(
                id=f"option_{uuid4().hex[:12]}",
                initiation_set=[{"context_vec_mean": start_context_vec.tolist()}],
                termination_condition={"reward_threshold": 0.8},
                policy_sequence=policy_sequence,
                expected_reward=chain_data.get("final_reward", 0.8),
                discovery_trace=nodes[0]["id"],
            )
            new_options_payload.append(option.model_dump())

        if not new_options_payload:  # <-- FIX: Correct variable name
            return

        query = """
        UNWIND $options AS opt
        CREATE (o:Option {id: opt.id})
        SET o += opt
        """
        await cypher_query(
            query,
            {"options": new_options_payload},
        )  # <-- FIX: Correct variable name
        print(
            f"[OptionMiner] Discovered and saved {len(new_options_payload)} new options.",
        )  # <-- FIX: Correct variable name


# Singleton export
option_miner = OptionMiner()
