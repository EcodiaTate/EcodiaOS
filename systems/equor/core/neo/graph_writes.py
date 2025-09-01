import uuid
from typing import Any

from core.utils.neo.cypher_query import cypher_query
from systems.equor.schemas import (
    Attestation,
    ComposeRequest,
    ComposeResponse,
    ConstitutionRule,
    Facet,
    Profile,
    QualiaState,
)

# Corrected Neo4j imports
from systems.synk.core.tools.neo import add_node, add_relationship


async def get_active_profile(agent: str, profile_name: str) -> dict[str, Any] | None:
    query = """
    MATCH (p:Profile {agent: $agent, name: $profile_name})
    WHERE NOT (p)-[:SUPERSEDED_BY]->()
    RETURN p
    LIMIT 1
    """
    result = await cypher_query(query, params={"agent": agent, "profile_name": profile_name})
    return result[0]["p"] if result else None


async def get_nodes_by_ids(node_ids: list[str]) -> list[dict[str, Any]]:
    if not node_ids:
        return []
    query = """
    MATCH (n)
    WHERE n.id IN $node_ids
    RETURN n
    """
    results = await cypher_query(query, params={"node_ids": node_ids})
    return [record["n"] for record in results]


async def save_prompt_patch(response: ComposeResponse, request: ComposeRequest) -> str:
    patch_properties = {
        "id": response.prompt_patch_id,
        "checksum": response.checksum,
        "text_summary": response.text[:256] + "...",
        "rcu_ref": response.rcu_ref,
        "episode_id": response.episode_id,
        "agent": request.agent,
        "profile_name": request.profile_name,
    }
    await add_node("PromptPatch", patch_properties)
    for facet_id in response.included_facets:
        await add_relationship(
            src_match={"label": "PromptPatch", "match": {"id": response.prompt_patch_id}},
            dst_match={"label": "Facet", "match": {"id": facet_id}},
            rel_type="DERIVED_FROM",
        )
    for rule_id in response.included_rules:
        await add_relationship(
            src_match={"label": "PromptPatch", "match": {"id": response.prompt_patch_id}},
            dst_match={"label": "ConstitutionRule", "match": {"id": rule_id}},
            rel_type="DERIVED_FROM",
        )
    return response.prompt_patch_id


async def save_attestation(attestation: Attestation) -> str:
    attestation_id = f"attest_{uuid.uuid4().hex}"
    properties = {"id": attestation_id, **attestation.model_dump(exclude_none=True)}
    await add_node("Attestation", properties)
    await add_relationship(
        src_match={"label": "Attestation", "match": {"id": attestation_id}},
        dst_match={"label": "PromptPatch", "match": {"id": attestation.applied_prompt_patch_id}},
        rel_type="USED",
    )
    await add_relationship(
        src_match={"label": "Episode", "match": {"id": attestation.episode_id}},
        dst_match={"label": "Attestation", "match": {"id": attestation_id}},
        rel_type="HAS_ATTESTATION",
    )
    return attestation_id


async def upsert_rules(rules: list[ConstitutionRule]) -> list[str]:
    if not rules:
        return []
    transaction_queries = []
    new_rule_ids = []
    for rule in rules:
        rule.id = rule.id or f"rule_{uuid.uuid4().hex}"
        new_rule_ids.append(rule.id)
        transaction_queries.append(
            {
                "statement": "MERGE (r:ConstitutionRule {id: $id}) SET r = $props, r.updated_at = datetime()",
                "parameters": {"id": rule.id, "props": rule.model_dump()},
            },
        )
        if rule.supersedes:
            transaction_queries.append(
                {
                    "statement": "MATCH (n:ConstitutionRule {id: $n_id}), (o:ConstitutionRule {id: $o_id}) MERGE (n)-[:SUPERSEDES]->(o)",
                    "parameters": {"n_id": rule.id, "o_id": rule.supersedes},
                },
            )
        for conflict_id in rule.conflicts_with:
            transaction_queries.append(
                {
                    "statement": "MATCH (a:ConstitutionRule {id: $a_id}), (b:ConstitutionRule {id: $b_id}) MERGE (a)-[:CONFLICTS_WITH]->(b)",
                    "parameters": {"a_id": rule.id, "b_id": conflict_id},
                },
            )
    for q in transaction_queries:
        await cypher_query(q["statement"], q["parameters"])
    return new_rule_ids


async def upsert_facet(facet: Facet) -> str:
    facet.id = facet.id or f"facet_{uuid.uuid4().hex}"
    await add_node("Facet", facet.model_dump())
    return facet.id


async def upsert_profile(profile: Profile) -> str:
    profile.id = profile.id or f"profile_{uuid.uuid4().hex}"
    await add_node("Profile", profile.model_dump())
    return profile.id


async def save_qualia_state(state: QualiaState) -> str:
    properties = state.model_dump()
    await add_node("QualiaState", properties)
    await add_relationship(
        src_match={"label": "Episode", "match": {"id": state.triggering_episode_id}},
        dst_match={"label": "QualiaState", "match": {"id": state.id}},
        rel_type="EXPERIENCED",
    )
    return state.id
