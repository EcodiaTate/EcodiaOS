# FINAL VERSION WITH PER-ARM FINGERPRINTING

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.policy.policy_dsl import PolicyGraph

# --------------------------
# Helpers
# --------------------------


def _coerce_policy_graph_to_dict(pg_like: dict[str, Any] | str | PolicyGraph) -> dict[str, Any]:
    """
    Accepts a dict, JSON string, or PolicyGraph object and returns a
    serializable dictionary, ready for storage in Neo4j.
    """
    if isinstance(pg_like, PolicyGraph):
        if hasattr(pg_like, "model_dump"):
            return pg_like.model_dump(mode="json")
        return json.loads(pg_like.json())
    if isinstance(pg_like, str):
        return json.loads(pg_like)
    if isinstance(pg_like, dict):
        return pg_like
    raise TypeError(f"Unsupported policy_graph type: {type(pg_like).__name__}")


def _fingerprint_dict(data: dict[str, Any]) -> str:
    """Stable SHA256 hash of JSON-serialized data."""
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def _get_existing_fingerprint(arm_id: str) -> str | None:
    result = await cypher_query(
        "MATCH (p:PolicyArm {id: $id}) RETURN p.fingerprint AS fp LIMIT 1",
        {"id": arm_id},
    )
    return (result or [{}])[0].get("fp")


# --------------------------
# Main Function
# --------------------------


async def register_arm(
    *,
    arm_id: str,
    mode: str,
    policy_graph: dict[str, Any] | str | PolicyGraph,
    head_state: dict[str, Any] | None = None,
) -> None:
    """
    High-efficiency upsert: skips write if the policy_graph has not changed.
    Also supports optional head_state updates.
    """
    pg_dict = _coerce_policy_graph_to_dict(policy_graph)
    fingerprint = _fingerprint_dict(pg_dict)

    existing_fp = await _get_existing_fingerprint(arm_id)
    if existing_fp == fingerprint:
        return  # ✅ Skip: arm already up-to-date

    # Main MERGE (create or update) with fingerprint
    await cypher_query(
        """
        MERGE (p:PolicyArm {id: $id})
        ON CREATE SET
          p.arm_id       = $arm_id,
          p.mode         = $mode,
          p.policy_graph = $pg_json,
          p.fingerprint  = $fp,
          p.created_at   = datetime()
        ON MATCH SET
          p.arm_id       = $arm_id,
          p.mode         = $mode,
          p.policy_graph = $pg_json,
          p.fingerprint  = $fp,
          p.updated_at   = datetime()
        """,
        {
            "id": arm_id,
            "arm_id": arm_id,
            "mode": mode,
            "pg_json": json.dumps(pg_dict, separators=(",", ":")),
            "fp": fingerprint,
        },
    )

    # Optional: Update bandit head state
    if head_state and all(v is not None for v in head_state.values()):
        await cypher_query(
            """
            MATCH (p:PolicyArm {id:$id})
            SET p.A = $A, p.A_shape = $A_shape,
                p.b = $b, p.b_shape = $b_shape,
                p.updated_at = datetime()
            """,
            {"id": arm_id, **head_state},
        )
