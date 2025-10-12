# systems/equor/core/neo/graph_writes.py
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from core.utils.neo.cypher_query import cypher_query
from systems.equor.schemas import (
    Attestation,
    ComposeRequest,
    ComposeResponse,
    ConstitutionRule,
    EcodiaCoreIdentity,
    Facet,
    InternalStateMetrics,
    Profile,
    QualiaState,
)

# Using synk helpers as provided
from systems.synk.core.tools.neo import add_node, add_relationship

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _coerce_version_number(v: Any) -> Any:
    """
    Ensure facet.version is numeric when possible.
    If it's a string that parses to a float, return the float; otherwise return original.
    """
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v
    return v


# ──────────────────────────────────────────────────────────────────────────────
# Core Identity
# ──────────────────────────────────────────────────────────────────────────────


async def upsert_core_identity(identity: EcodiaCoreIdentity) -> str:
    """
    Upsert a new EcodiaCoreIdentity node and link the previous to the new one via
    (old)-[:SUPERSEDED_BY]->(new). Stable across retries.
    """
    query = """
    MERGE (new_id:EcodiaCoreIdentity {id: $props.id})
    ON CREATE SET new_id.created_at = datetime()
    SET new_id += $props, new_id.updated_at = datetime()
    WITH new_id
    OPTIONAL MATCH (old_id:EcodiaCoreIdentity {id: $supersedes_id})
    WHERE old_id.id <> new_id.id
    FOREACH (_ IN CASE WHEN old_id IS NOT NULL THEN [1] ELSE [] END |
        MERGE (old_id)-[:SUPERSEDED_BY]->(new_id)
    )
    RETURN new_id.id AS id
    """
    params = {
        "props": identity.model_dump(),
        "supersedes_id": getattr(identity, "supersedes", None),
    }
    result = await cypher_query(query, params) or []
    return (result[0] or {}).get("id") or identity.id


# ──────────────────────────────────────────────────────────────────────────────
# Profiles & Nodes
# ──────────────────────────────────────────────────────────────────────────────


async def get_active_profile(agent: str, profile_name: str) -> dict[str, Any] | None:
    """
    Fetch the latest (unsuperseded) Profile for an agent/name.
    """
    query = """
    MATCH (p:Profile {agent: $agent, name: $profile_name})
    WHERE NOT (p)-[:SUPERSEDED_BY]->()
    RETURN p AS profile
    LIMIT 1
    """
    result = await cypher_query(query, params={"agent": agent, "profile_name": profile_name}) or []
    rec = result[0] or {}
    return rec.get("profile")


async def get_nodes_by_ids(node_ids: list[str]) -> list[dict[str, Any]]:
    """
    Return raw node property dicts plus their labels for the provided IDs.
    """
    if not node_ids:
        return []
    query = """
    MATCH (n)
    WHERE n.id IN $node_ids
    RETURN n AS node, labels(n) AS labels
    """
    results = await cypher_query(query, params={"node_ids": node_ids}) or []
    out: list[dict[str, Any]] = []
    for record in results:
        node_props = record.get("node") or {}
        labels = record.get("labels") or []
        if isinstance(node_props, dict):
            out.append({**node_props, "labels": labels})
        else:
            out.append({"node": node_props, "labels": labels})
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Prompt Patch / Attestations
# ──────────────────────────────────────────────────────────────────────────────


async def save_prompt_patch(response: ComposeResponse, request: ComposeRequest) -> str:
    """
    Persist a PromptPatch with shallow provenance and connect derived inputs.
    """
    patch_properties = {
        "id": response.prompt_patch_id,
        "checksum": response.checksum,
        "text_summary": (
            (response.text or "")[:256]
            + ("..." if response.text and len(response.text) > 256 else "")
        ),
        "rcu_ref": response.rcu_ref,
        "episode_id": response.episode_id,
        "agent": request.agent,
        "profile_name": request.profile_name,
        "created_at": str(getattr(response, "created_at", "")) or None,
    }
    await add_node(["PromptPatch"], patch_properties)

    for facet_id in getattr(response, "included_facets", []) or []:
        await add_relationship(
            src_match={"label": "PromptPatch", "match": {"id": response.prompt_patch_id}},
            dst_match={"label": "Facet", "match": {"id": facet_id}},
            rel_type="DERIVED_FROM",
        )

    for rule_id in getattr(response, "included_rules", []) or []:
        await add_relationship(
            src_match={"label": "PromptPatch", "match": {"id": response.prompt_patch_id}},
            dst_match={"label": "ConstitutionRule", "match": {"id": rule_id}},
            rel_type="DERIVED_FROM",
        )
    return response.prompt_patch_id


async def save_attestation(attestation: Attestation) -> str:
    """
    Create an Attestation and connect it to the applied PromptPatch and its Episode.
    """
    attestation_id = f"attest_{uuid.uuid4().hex}"
    properties = {"id": attestation_id, **attestation.model_dump(exclude_none=True)}
    await add_node(["Attestation"], properties)

    if getattr(attestation, "applied_prompt_patch_id", None):
        await add_relationship(
            src_match={"label": "Attestation", "match": {"id": attestation_id}},
            dst_match={
                "label": "PromptPatch",
                "match": {"id": attestation.applied_prompt_patch_id},
            },
            rel_type="USED",
        )

    if getattr(attestation, "episode_id", None):
        await add_relationship(
            src_match={"label": "Episode", "match": {"id": attestation.episode_id}},
            dst_match={"label": "Attestation", "match": {"id": attestation_id}},
            rel_type="HAS_ATTESTATION",
        )
    return attestation_id


# ──────────────────────────────────────────────────────────────────────────────
# Rules
# ──────────────────────────────────────────────────────────────────────────────


async def upsert_rules(rules: list[ConstitutionRule]) -> list[str]:
    """
    Idempotently upsert ConstitutionRule nodes and define relationships:
      - (new)-[:SUPERSEDES]->(old)
      - (a)-[:CONFLICTS_WITH]->(b)
    """
    if not rules:
        return []

    new_rule_ids: list[str] = []

    for rule in rules:
        rule.id = rule.id or f"rule_{uuid.uuid4().hex}"
        new_rule_ids.append(rule.id)

        # Upsert node
        await cypher_query(
            """
            MERGE (r:ConstitutionRule {id: $id})
            ON CREATE SET r.created_at = datetime()
            SET r += $props, r.updated_at = datetime()
            """,
            {"id": rule.id, "props": rule.model_dump()},
        )

        # Supersedes
        if getattr(rule, "supersedes", None):
            await cypher_query(
                """
                MATCH (n:ConstitutionRule {id: $n_id}), (o:ConstitutionRule {id: $o_id})
                MERGE (n)-[:SUPERSEDES]->(o)
                """,
                {"n_id": rule.id, "o_id": rule.supersedes},
            )

        # Conflicts
        for conflict_id in getattr(rule, "conflicts_with", []) or []:
            await cypher_query(
                """
                MATCH (a:ConstitutionRule {id: $a_id}), (b:ConstitutionRule {id: $b_id})
                MERGE (a)-[:CONFLICTS_WITH]->(b)
                """,
                {"a_id": rule.id, "b_id": conflict_id},
            )

    return new_rule_ids


# ──────────────────────────────────────────────────────────────────────────────
# Facets / Profiles
# ──────────────────────────────────────────────────────────────────────────────


async def upsert_facet(facet: Facet) -> str:
    """
    Upsert a Facet node with normalized version. Uses MERGE for idempotency.
    """
    facet.id = facet.id or f"facet_{uuid.uuid4().hex}"

    facet_dict = facet.model_dump()
    if "version" in facet_dict:
        facet_dict["version"] = _coerce_version_number(facet_dict["version"])

    query = """
    MERGE (f:Facet {id: $id})
    ON CREATE SET f.created_at = datetime()
    SET f += $props, f.updated_at = datetime()
    RETURN f.id AS id
    """
    res = await cypher_query(query, {"id": facet.id, "props": facet_dict}) or []
    return (res[0] or {}).get("id") or facet.id


async def upsert_profile(profile: Profile) -> str:
    """
    Upsert a Profile node (agent + name + content).
    """
    profile.id = profile.id or f"profile_{uuid.uuid4().hex}"
    query = """
    MERGE (p:Profile {id: $id})
    ON CREATE SET p.created_at = datetime()
    SET p += $props, p.updated_at = datetime()
    RETURN p.id AS id
    """
    res = await cypher_query(query, {"id": profile.id, "props": profile.model_dump()}) or []
    return (res[0] or {}).get("id") or profile.id


# ──────────────────────────────────────────────────────────────────────────────
# Qualia / Metrics
# ──────────────────────────────────────────────────────────────────────────────


async def save_qualia_state(state: QualiaState) -> str:
    """
    Persist a QualiaState and link it to the triggering Episode.
    """
    properties = state.model_dump()
    await add_node(["QualiaState"], properties)

    if getattr(state, "triggering_episode_id", None):
        await add_relationship(
            src_match={"label": "Episode", "match": {"id": state.triggering_episode_id}},
            dst_match={"label": "QualiaState", "match": {"id": state.id}},
            rel_type="EXPERIENCED",
        )
    return state.id


async def attach_metrics_to_episode(metrics: InternalStateMetrics) -> None:
    """
    Attach raw internal metrics as properties on an Episode node, prefixed with metric_.
    """
    episode_id = metrics.episode_id
    if hasattr(metrics, "model_dump"):
        metrics_dict = metrics.model_dump()
    else:
        # pydantic v1 compatibility
        metrics_dict = metrics.dict()  # type: ignore[attr-defined]

    props_to_set = {f"metric_{k}": v for k, v in metrics_dict.items() if k != "episode_id"}

    query = """
    MATCH (e:Episode {id: $episode_id})
    SET e += $props, e.metrics_updated_at = datetime()
    RETURN e
    """
    params = {"episode_id": episode_id, "props": props_to_set}
    await cypher_query(query, params)


__all__ = [
    "upsert_core_identity",
    "get_active_profile",
    "get_nodes_by_ids",
    "save_prompt_patch",
    "save_attestation",
    "upsert_rules",
    "upsert_facet",
    "upsert_profile",
    "save_qualia_state",
    "attach_metrics_to_episode",
]
