# systems/unity/core/neo/graph_writes.py
from __future__ import annotations

import json
import uuid
from typing import Any

from core.utils.neo.cypher_query import cypher_query
from systems.synk.core.tools.neo import add_node, add_relationship
from systems.unity.schemas import DeliberationSpec, VerdictModel


def _jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, bool | int | float | str):
        return obj
    if isinstance(obj, list | tuple | set):
        return [_jsonable(x) for x in list(obj)]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    md = getattr(obj, "model_dump", None)
    if callable(md):
        return _jsonable(md())
    dct = getattr(obj, "__dict__", None)
    if isinstance(dct, dict):
        return _jsonable(dct)
    return str(obj)


async def create_deliberation_node(
    episode_id: str,
    spec: DeliberationSpec,
    rcu_start_ref: str,
) -> str:
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
        "created_at": None,  # allow DB default datetime()
    }
    await add_node("Deliberation", props)
    return deliberation_id


async def annotate_deliberation(deliberation_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields = _jsonable(fields)
    await cypher_query(
        "MATCH (d:Deliberation {id:$id}) SET d += $fields RETURN d.id",
        {"id": deliberation_id, "fields": fields},
    )


async def record_transcript_chunk(deliberation_id: str, turn: int, role: str, content: str) -> str:
    chunk_id = f"tc_{uuid.uuid4().hex}"
    await add_node(
        "TranscriptChunk",
        {
            "id": chunk_id,
            "deliberation_id": deliberation_id,
            "turn": int(turn),
            "role": role,
            "content": content,
        },
    )
    await add_relationship(
        src_match={"label": "Deliberation", "match": {"id": deliberation_id}},
        dst_match={"label": "TranscriptChunk", "match": {"id": chunk_id}},
        rel_type="HAS_TRANSCRIPT",
    )
    return chunk_id


async def create_artifact(deliberation_id: str, artifact_type: str, body: dict[str, Any]) -> str:
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
    verdict_id = f"verdict_{uuid.uuid4().hex}"
    vprops = {"id": verdict_id, "rcu_end_ref": rcu_end_ref, **_jsonable(verdict)}
    await add_node("Verdict", vprops)
    await add_relationship(
        src_match={"label": "Deliberation", "match": {"id": deliberation_id}},
        dst_match={"label": "Verdict", "match": {"id": verdict_id}},
        rel_type="RESULTED_IN",
    )
    await cypher_query(
        """
        MATCH (d:Deliberation {id:$id})
        SET d.status = 'completed', d.rcu_end_ref = $rcu
        """,
        {"id": deliberation_id, "rcu": rcu_end_ref},
    )
    return verdict_id
