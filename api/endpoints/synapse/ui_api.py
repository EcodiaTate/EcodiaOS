# systems/synapse/values/ui_api.py
# NEW FILE
from typing import Any

from fastapi import APIRouter, HTTPException

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.schemas import ComparisonPairResponse, EpisodeSummary, SubmitPreferenceRequest

router = APIRouter(prefix="/values", tags=["Synapse Alignment"])


@router.get("/get_comparison_pair", response_model=ComparisonPairResponse)
async def get_comparison_pair():
    """
    Fetches two recent, comparable episodes that have not yet been compared.
    """
    # This query finds two episodes with the same task_key that don't already
    # have a PREFERENCE relationship between them.
    query = """
    MATCH (a:Episode), (b:Episode)
    WHERE a.task_key = b.task_key AND id(a) < id(b)
      AND a.reward IS NOT NULL AND b.reward IS NOT NULL
    AND NOT EXISTS((a)-[:CHOSE|REJECTED]-(:Preference)-[:CHOSE|REJECTED]-(b))
    RETURN a, b
    LIMIT 1
    """
    result = await cypher_query(query)
    if not result:
        raise HTTPException(status_code=404, detail="No comparable episode pairs found.")

    def to_summary(ep_data: dict[str, Any]) -> EpisodeSummary:
        return EpisodeSummary(
            episode_id=ep_data["id"],
            goal=ep_data["context"].get("goal", "N/A"),
            champion_arm_id=ep_data["chosen_arm_id"],
            reward_scalar=ep_data["reward"],
            reward_vector=ep_data["reward_vec"],
            outcome_summary=ep_data["metrics"],
        )

    return ComparisonPairResponse(
        episode_a=to_summary(result[0]["a"]),
        episode_b=to_summary(result[0]["b"]),
    )


@router.post("/submit_preference")
async def submit_preference(req: SubmitPreferenceRequest):
    """
    Ingests a human preference, creating a Preference node in the graph.
    """
    query = """
    MATCH (winner:Episode {id: $winner_id})
    MATCH (loser:Episode {id: $loser_id})
    CREATE (winner)<-[:CHOSE]-(p:Preference {
        id: randomUUID(),
        reasoning: $reasoning,
        created_at: datetime()
    })-[:REJECTED]->(loser)
    RETURN p.id AS preference_id
    """
    result = await cypher_query(
        query,
        {
            "winner_id": req.winner_episode_id,
            "loser_id": req.loser_episode_id,
            "reasoning": req.reasoning,
        },
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to create preference in graph.")

    return {"status": "accepted", "preference_id": result[0]["preference_id"]}
