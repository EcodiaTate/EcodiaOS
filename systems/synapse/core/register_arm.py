from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.sdk.client import SynapseClient


async def register_arm(*, arm_id: str, mode: str, config: dict[str, Any]) -> None:
    """
    Write a new PolicyArm into graph and trigger registry reload.
    Ensures both id and arm_id exist (firewall vs. loader requirements).
    """
    req = {"model", "temperature"}
    missing = [k for k in req if k not in config]
    if missing:
        raise ValueError(f"PolicyArm '{arm_id}' missing required config keys: {missing}")

    q = """
    MERGE (p:PolicyArm {id: $id})
    ON CREATE SET p.arm_id = $arm_id, p.mode = $mode, p.config = $cfg, p.created_at = datetime()
    ON MATCH  SET p.arm_id = $arm_id, p.mode = $mode, p.config = $cfg, p.updated_at = datetime()
    """
    await cypher_query(q, {"id": arm_id, "arm_id": arm_id, "mode": mode, "cfg": config})

    sc = SynapseClient()
    await sc.registry_reload()
