from __future__ import annotations

import json
import uuid
from typing import Any

from core.utils.neo.cypher_query import cypher_query
from systems.synk.core.tools.neo import add_node, add_relationship
from systems.unity.schemas import DeliberationSpec, VerdictModel


def _jsonable(obj: Any) -> Any:
    """A helper function to safely serialize complex objects to JSON."""
    if obj is None or isinstance(obj, bool | int | float | str):
        return obj
    if isinstance(obj, list | tuple | set):
        return [_jsonable(x) for x in list(obj)]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    md = getattr(obj, "model_dump", None)
    if callable(md):
        return _jsonable(md())
    return str(obj)


async def create_deliberation_node(
    episode_id: str, spec: DeliberationSpec, rcu_start_ref: str
) -> str:
    """Creates the main Deliberation node in the graph."""
    deliberation_id = f"delib_{uuid.uuid4().hex}"
    props = {
        "id": deliberation_id,
        "episode_id": episode_id,
        "topic": spec.topic,
        "goal": spec.goal,
        "protocol_hint": getattr(spec, "protocol_hint", None),
        "rcu_start_ref": rcu_start_ref,
        "status": "started",
        "spec": json.dumps(_jsonable(spec), separators=(",", ":"), ensure_ascii=False),
    }
    await cypher_query(
        """
        MERGE (d:Deliberation {id: $id})
        ON CREATE SET d.created_at = datetime()
        SET d += $props
        """,
        {"id": deliberation_id, "props": props},
    )
    return deliberation_id


async def annotate_deliberation(deliberation_id: str, **fields: Any) -> None:
    """Adds or updates properties on an existing Deliberation node."""
    if not fields:
        return

    # FIX: Explicitly serialize any nested dictionary values to JSON strings.
    sanitized_fields = {}
    for key, value in fields.items():
        if isinstance(value, dict):
            sanitized_fields[key] = json.dumps(
                _jsonable(value), separators=(",", ":"), ensure_ascii=False
            )
        else:
            sanitized_fields[key] = value

    await cypher_query(
        "MATCH (d:Deliberation {id:$id}) SET d += $fields",
        {"id": deliberation_id, "fields": sanitized_fields},
    )


async def record_transcript_chunk(deliberation_id: str, turn: int, role: str, content: str) -> str:
    """Creates a TranscriptChunk and atomically links it to the Deliberation."""
    chunk_id = f"tc_{uuid.uuid4().hex}"
    props = {
        "id": chunk_id,
        "deliberation_id": deliberation_id,
        "turn": int(turn),
        "role": role,
        "content": content,
    }
    await cypher_query(
        """
        MATCH (d:Deliberation {id: $deliberation_id})
        CREATE (t:TranscriptChunk $props)
        MERGE (d)-[:HAS_TRANSCRIPT]->(t)
        """,
        {"deliberation_id": deliberation_id, "props": props},
    )
    return chunk_id


async def create_artifact(deliberation_id: str, artifact_type: str, body: dict[str, Any]) -> str:
    """Creates an Artifact node (e.g., for a plan or search tree) and links it."""
    art_id = f"art_{uuid.uuid4().hex}"
    await add_node(
        "Artifact",
        {
            "id": art_id,
            "type": artifact_type,
            "body": json.dumps(_jsonable(body), separators=(",", ":"), ensure_ascii=False),
        },
    )
    await add_relationship(
        src_match={"label": "Deliberation", "match": {"id": deliberation_id}},
        dst_match={"label": "Artifact", "match": {"id": art_id}},
        rel_type="HAS_ARTIFACT",
    )
    return art_id


async def upsert_claim(deliberation_id: str, claim_text: str, created_by_role: str) -> str:
    """Creates a Claim node for use in an argument map."""
    claim_id = f"claim_{uuid.uuid4().hex}"
    await add_node(
        "Claim",
        {
            "id": claim_id,
            "text": claim_text,
            "created_by": created_by_role,
        },
    )
    await add_relationship(
        src_match={"label": "Deliberation", "match": {"id": deliberation_id}},
        dst_match={"label": "Claim", "match": {"id": claim_id}},
        rel_type="HAS_CLAIM",
    )
    return claim_id


async def link_support_or_attack(
    from_node_id: str,
    from_node_label: str,
    to_node_id: str,
    to_node_label: str,
    rel_type: str,
    rationale: str,
) -> str:
    """Creates a Support or Attack node to link two other nodes."""
    link_id = f"{rel_type.lower()}_{uuid.uuid4().hex}"
    link_label = "Support" if rel_type == "SUPPORTED_BY" else "Attack"

    await add_node(link_label, {"id": link_id, "rationale": rationale})
    await add_relationship(
        src_match={"label": from_node_label, "match": {"id": from_node_id}},
        dst_match={"label": link_label, "match": {"id": link_id}},
        rel_type=rel_type,
    )
    await add_relationship(
        src_match={"label": link_label, "match": {"id": link_id}},
        dst_match={"label": to_node_label, "match": {"id": to_node_id}},
        rel_type="TARGETS",
    )
    return link_id


async def finalize_verdict(deliberation_id: str, verdict: VerdictModel, rcu_end_ref: str) -> str:
    """Creates the final Verdict node, links it, and updates the Deliberation status."""
    verdict_id = f"verdict_{uuid.uuid4().hex}"
    vprops = {"id": verdict_id, "rcu_end_ref": rcu_end_ref, **_jsonable(verdict)}

    await cypher_query(
        """
        MATCH (d:Deliberation {id: $deliberation_id})
        CREATE (v:Verdict $props)
        MERGE (d)-[:RESULTED_IN]->(v)
        SET d.status = 'completed', d.rcu_end_ref = $rcu_end_ref
        """,
        {
            "deliberation_id": deliberation_id,
            "props": vprops,
            "rcu_end_ref": rcu_end_ref,
        },
    )
    return verdict_id
