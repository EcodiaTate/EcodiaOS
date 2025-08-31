# systems/synk/core/listeners/conflict_ingestor.py
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional

from core.utils.neo.cypher_query import cypher_query
from systems.synk.core.tools.neo import create_conflict_node

EVIDENCE_BYTES_MAX = 8000


def _now_ms() -> int:
    return int(time.time() * 1000)


def _extract_conflict_uuid(node: Any) -> Optional[str]:
    """
    Accepts various return shapes from create_conflict_node and extracts the UUID/id.
    Looks in common places: properties.uuid / uuid / conflict_id / id / event_id.
    """
    if node is None:
        return None
    if isinstance(node, dict):
        props = node.get("properties") if isinstance(node.get("properties"), dict) else node
        for k in ("uuid", "conflict_id", "id", "event_id"):
            v = props.get(k) if isinstance(props, dict) else None
            if v:
                return str(v)
    # Last resort: attribute access
    for k in ("uuid", "conflict_id", "id", "event_id"):
        if hasattr(node, k):
            v = getattr(node, k)
            if v:
                return str(v)
    return None


def _normalize_severity(s: Any) -> str:
    s = str(s or "medium").lower()
    return s if s in {"low", "medium", "high", "critical"} else "medium"


async def on_conflict_detected(payload: Dict[str, Any]) -> None:
    """
    Listener for 'conflict_detected' events.
    - Upserts a Conflict node (via create_conflict_node)
    - Hashes & stores a stack trace as Evidence
    - Links Conflict -[:HAS_EVIDENCE]-> Evidence (single Cypher; no disconnected pattern)
    """
    component = payload.get("component") or payload.get("system") or "unknown"
    print(f"[Conflict Ingestor] Received conflict from component: {component}")

    try:
        # ---------- Prepare evidence ----------
        stack_blob = payload.get("stack_blob") or ""
        # ensure text; replace invalid bytes if any
        if not isinstance(stack_blob, str):
            stack_blob = str(stack_blob)
        ev_sha = hashlib.sha256(stack_blob.encode("utf-8", "replace")).hexdigest()
        ev_bytes = stack_blob[:EVIDENCE_BYTES_MAX]

        # ---------- Create/ensure Conflict ----------
        conflict_node = await create_conflict_node(
            system=component,
            description=payload.get("description") or "",
            origin_node_id=payload.get("signature") or payload.get("origin_id"),
            additional_data={
                "severity": _normalize_severity(payload.get("severity")),
                "version": payload.get("version") or "",
                "etype": payload.get("etype") or "",
                "source_system": payload.get("source_system") or "synk",
                "t": _now_ms(),
                # context (will be JSON-stringified by cypher param sanitizer if nested)
                **(payload.get("context") or {}),
            },
        )
        conflict_id = _extract_conflict_uuid(conflict_node)
        if not conflict_id:
            print("!!! CRITICAL: Failed to obtain conflict UUID from create_conflict_node() result")
            return

        # ---------- Evidence + Relationship (single query; no cartesian product) ----------
        await cypher_query(
            """
            UNWIND [$row] AS row
            // Match existing conflict by uuid/id/event_id for resilience
            MATCH (c:Conflict)
            WHERE c.uuid = row.src.uuid OR c.conflict_id = row.src.uuid OR c.id = row.src.uuid OR c.event_id = row.src.uuid

            // Upsert Evidence and relationship in one go
            MERGE (e:Evidence { sha: row.dst.sha })
            ON CREATE SET
              e.type  = row.dst.type,
              e.bytes = row.dst.bytes,
              e.t     = row.dst.t
            ON MATCH SET
              e.type  = coalesce(e.type, row.dst.type),
              e.bytes = coalesce(e.bytes, row.dst.bytes)

            MERGE (c)-[r:HAS_EVIDENCE]->(e)
            ON CREATE SET r += row.rel_props
            """,
            {
                "row": {
                    "src": {"uuid": conflict_id},
                    "dst": {"sha": ev_sha, "type": "stack", "bytes": ev_bytes, "t": _now_ms()},
                    "rel_props": {"t": _now_ms(), "source": "synk"},
                }
            },
        )

    except Exception as e:
        # Final safety net: never let this explode upstream
        print(f"!!! CRITICAL: Failed to write conflict to graph: {e}")
