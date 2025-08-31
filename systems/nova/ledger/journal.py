from __future__ import annotations

from typing import Any

from systems.synk.core.tools.neo import add_node, add_relationship


async def write_capsule(capsule: dict[str, Any]) -> None:
    """
    Persist a DesignCapsule-like dict to Neo4j. Mirrors Evo's graph hygiene.
    """
    cid = capsule.get("capsule_id")
    await add_node(labels=["NovaDesignCapsule"], properties={"event_id": cid, "body": capsule})
    # Link artifacts if present
    for art in capsule.get("artifacts", []):
        aid = art.get("barcode") or art.get("hash") or ""
        if not aid:
            continue
        await add_node(labels=["NovaArtifact"], properties={"event_id": aid, "body": art})
        await add_relationship(
            src_match={"label": "NovaDesignCapsule", "match": {"event_id": cid}},
            dst_match={"label": "NovaArtifact", "match": {"event_id": aid}},
            rel_type="CONTAINS",
        )


async def write_whytrace(why: dict[str, Any]) -> None:
    did = (why.get("provenance") or {}).get("decision_id", "")
    await add_node(labels=["NovaWhyTrace"], properties={"decision_id": did, "body": why})
