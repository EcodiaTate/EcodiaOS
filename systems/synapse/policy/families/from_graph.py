# systems/synapse/policy/families/from_graph.py

from typing import List

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry_bootstrap import ArmStrategyTemplate


async def load_strategy_templates(family_id: str) -> list[ArmStrategyTemplate]:
    query = """
    MATCH (f:ArmFamily {family_id: $fid})-[:HAS_STRATEGY]->(s:StrategyTemplate)
    RETURN s.name AS name, s.tags AS tags
    """
    rows = await cypher_query(query, {"fid": family_id})
    return [
        ArmStrategyTemplate(name=row["name"], tags=row.get("tags", []))
        for row in rows
        if row.get("name")
    ]
