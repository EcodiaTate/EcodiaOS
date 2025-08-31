# systems/synapse/core/episode.py
from __future__ import annotations

import json
import uuid
from typing import Any

from core.utils.neo.cypher_query import cypher_query


def _jsonable(obj: Any) -> Any:
    """Deeply and safely converts an object to be JSON-serializable for Neo4j."""
    if obj is None or isinstance(obj, bool | int | float | str):
        return obj
    if isinstance(obj, list | tuple | set):
        return [_jsonable(x) for x in list(obj)]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    # Fallback for Pydantic models or other objects
    md = getattr(obj, "model_dump", getattr(obj, "dict", None))
    if callable(md):
        return _jsonable(md())
    return str(obj)


async def start_episode(
    *,
    mode: str,
    task_key: str,
    chosen_arm_id: str | None = None,
    parent_episode_id: str | None = None,
    context: dict[str, Any] | None = None,
    audit_trace: dict[str, Any] | None = None,
) -> str:
    """
    Creates a new Episode node in Neo4j with JSON-string properties.
    This is the single, authoritative function for episode creation.
    """
    episode_id = str(uuid.uuid4())
    q = """
    MERGE (e:Episode {id: $id})
    SET e.mode = $mode,
        e.task_key = $task_key,
        e.chosen_arm_id = $arm,
        e.parent_episode_id = $parent,
        e.context_json = $context_json,
        e.audit_trace_json = $audit_trace_json,
        e.created_at = coalesce(e.created_at, datetime())
    """
    await cypher_query(
        q,
        {
            "id": episode_id,
            "mode": mode,
            "task_key": task_key,
            "arm": chosen_arm_id,
            "parent": parent_episode_id,
            "context_json": json.dumps(_jsonable(context or {})),
            "audit_trace_json": json.dumps(_jsonable(audit_trace or {})),
        },
    )
    return episode_id


# We are intentionally removing end_episode from this file to ensure
# all outcome logging goes through the correct path in reward.py.
