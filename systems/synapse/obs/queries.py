# systems/synapse/obs/queries.py
# NEW FILE
from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.qd.map_elites import qd_archive
from systems.synapse.qd.replicator import replicator


async def get_global_stats() -> dict[str, Any]:
    """Fetches high-level aggregate statistics for the system."""
    query = """
    MATCH (e:Episode)
    WITH count(e) AS total_episodes
    MATCH (p:PolicyArm)
    WITH total_episodes, count(p) AS total_arms
    MATCH (f:Episode) WHERE f.audit_trace.firewall_verdict.is_safe = false
    RETURN total_episodes, total_arms, count(f) AS firewall_blocks
    """
    result = await cypher_query(query)
    stats = result[0] if result else {}

    return {
        "total_episodes": stats.get("total_episodes", 0),
        "total_arms": stats.get("total_arms", 0),
        "active_niches": len(qd_archive._archive),
        "reward_per_dollar_p50": 0.0,  # Placeholder until cost tracking is deeper
        "firewall_blocks_total": stats.get("firewall_blocks", 0),
        "genesis_mints_total": 0,  # Placeholder
        "genesis_prunes_total": 0,  # Placeholder
    }


async def get_qd_coverage_data() -> dict[str, Any]:
    """Assembles data on the state of the Quality-Diversity archive."""
    niches = []
    for niche, data in qd_archive._archive.items():
        niches.append(
            {
                "niche": niche,
                "champion_arm_id": data["arm_id"],
                "score": data["score"],
                "fitness_share": replicator._niche_share.get(niche, 0.0),
            },
        )

    total_possible_niches = 1  # Placeholder, a real system would define the space
    coverage = len(niches) / total_possible_niches if total_possible_niches > 0 else 0

    return {
        "coverage_percentage": coverage * 100,
        "niches": sorted(niches, key=lambda x: x["fitness_share"], reverse=True),
    }


async def get_full_episode_trace(episode_id: str) -> dict[str, Any] | None:
    """Retrieves and reconstructs the full audit trace for a single episode."""
    query = """
    MATCH (e:Episode {id: $episode_id})
    RETURN e.context AS request_context,
           e.audit_trace AS audit_trace,
           e.metrics AS outcome_metrics,
           e.reward AS reward_scalar,
           e.reward_vec AS reward_vector
    LIMIT 1
    """
    result = await cypher_query(query, {"episode_id": episode_id})
    if not result:
        return None

    data = result[0]
    audit = data.get("audit_trace", {})

    return {
        "episode_id": episode_id,
        "request_context": data.get("request_context", {}),
        "ood_check": audit.get("ood_check", {}),
        "cognitive_strategy": audit.get("cognitive_strategy", {}),
        "bandit_scores": audit.get("bandit_scores", {}),
        "critic_reranked_champion": audit.get("critic_reranked_champion"),
        "final_economic_scores": audit.get("final_economic_scores", {}),
        "simulation_prediction": audit.get("simulator_pred", {}),
        "firewall_verdict": audit.get("firewall_verdict", {}),
        "final_champion_id": data.get("outcome_metrics", {}).get("chosen_arm_id"),
        "outcome_metrics": data.get("outcome_metrics", {}),
        "reward_scalar": data.get("reward_scalar"),
        "reward_vector": data.get("reward_vector"),
        "explanation": audit.get("explanation", {}),
        "rcu_snapshot": audit.get("snapshots", {}),
    }
