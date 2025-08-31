# systems/evo/conflicts/store.py
# DESCRIPTION: Canonical, robust conflict service with deduplication, background
# persistence, and intelligent data coercion.

from __future__ import annotations

import asyncio
import time
import uuid
from hashlib import sha256
from typing import Any, Dict, List, Optional

from core.llm.embeddings_gemini import get_embedding
from core.utils.net_api import ENDPOINTS, post_internal
from core.utils.neo.cypher_query import cypher_query
from core.utils.time import now_iso
from systems.evo.schemas import ConflictID, ConflictNode, ConflictStatus
# Local import to avoid circular dependency at module load time.
from systems.synk.core.tools.neo import add_node


async def create_conflict_node(
    system: str,
    description: str,
    origin_node_id: str, # signature from orchestrator
    additional_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Creates a Conflict node, computes its semantic embedding, persists it,
    and notifies the Evo patrol for potential escalation. 
    """
    data = additional_data or {}
    embedding: list[float] | None = None
    try:
        # Embed the goal or description for semantic search. 
        embed_text = data.get("goal", description)
        embedding = await get_embedding(embed_text, task_type="RETRIEVAL_DOCUMENT")
    except Exception:
        embedding = [] # Never fail on embedding generation

    conflict_cid = str(uuid.uuid4())
    conflict_props = {
        "conflict_id": conflict_cid,
        "system": system,
        "source_system": system,
        "description": description,
        "origin_node_id": origin_node_id,
        "severity": (data.get("severity") or "medium").lower(),
        "status": "open",
        "created_at": now_iso(),
        "embedding": embedding or [],
        "context": data, # Store full context for analysis 
    }

    conflict_node = await add_node(labels=["Conflict"], properties=conflict_props)

    # Best-effort notification to Evo. Failures are logged but do not block. 
    try:
        evo_payload = {"conflict_id": conflict_cid, "description": description}
        headers = {"x-ecodia-immune": "1"} # Internal call, bypass some guards
        await post_internal(ENDPOINTS.EVO_ESCALATE, json=evo_payload, headers=headers, timeout=10.0)
    except Exception as e:
        print(f"[ConflictStore] WARNING: Failed to notify Evo patrol for {conflict_cid}. Error: {e}")

    return conflict_node


class ConflictsService:
    """
    An intelligent, in-memory conflict store with background persistence.
    Provides deduplication to prevent alert storms and safe data access patterns.
    """

    def __init__(self, cooldown_sec: int = 60):
        self._by_id: dict[str, ConflictNode] = {}
        self._seen: dict[str, float] = {}  # fingerprint -> timestamp
        self._cooldown = cooldown_sec

    def _fingerprint(self, node: ConflictNode) -> str:
        """Creates a stable hash to identify duplicate conflicts."""
        key = "|".join([
            node.source_system,
            node.kind,
            (node.description or "")[:128],
        ])
        return sha256(key.encode("utf-8")).hexdigest()

    def _coerce_node(self, item: ConflictNode | Dict[str, Any]) -> ConflictNode:
        """Safely coerces a dict into a schema-valid ConflictNode."""
        if isinstance(item, ConflictNode):
            return item
        data = dict(item or {})
        # Ensure critical fields have safe defaults so downstream consumers don't crash.
        data.setdefault("conflict_id", str(uuid.uuid4()))
        data.setdefault("source_system", "unknown")
        data.setdefault("description", "")
        data.setdefault("context", {})
        data.setdefault("severity", "medium")
        data.setdefault("status", "open")
        data.setdefault("spec_coverage", {"has_spec": False, "gaps": []}) # 
        return ConflictNode(**data)

    def batch(self, conflicts: List[ConflictNode | Dict[str, Any]]) -> Dict[str, Any]:
        """
        Intakes a batch of conflicts, applies deduplication, updates the in-memory
        store, and schedules a background task to persist them to the graph.
        """
        if not conflicts:
            return {"ok": True, "upserts": 0, "ids": []}

        now = time.time()
        accepted_nodes: List[ConflictNode] = []
        all_ids: List[str] = []

        for item in conflicts:
            node = self._coerce_node(item)
            all_ids.append(node.conflict_id)
            fp = self._fingerprint(node)

            # DEDUPLICATION: If we've seen this fingerprint within the cooldown, skip it.
            if (now - self._seen.get(fp, 0)) < self._cooldown:
                continue

            self._seen[fp] = now
            self._by_id[node.conflict_id] = node
            accepted_nodes.append(node)

        # PERSISTENCE: Run the graph write in the background to avoid blocking the caller.
        if accepted_nodes:
            rows = [self._row_for_upsert(n) for n in accepted_nodes]
            try:
                asyncio.get_running_loop().create_task(self._persist_rows(rows))
            except RuntimeError:
                asyncio.run(self._persist_rows(rows))

        return {"ok": True, "upserts": len(accepted_nodes), "ids": all_ids}

    def get(self, conflict_id: str) -> ConflictNode:
        """Strictly retrieves a conflict, raising KeyError if not found."""
        return self._by_id[conflict_id]

    def peek(self, conflict_id: str) -> Optional[ConflictNode]:
        """Safely retrieves a conflict, returning None if not found."""
        return self._by_id.get(conflict_id)

    def list_open(self, *, limit: int | None = None) -> list[ConflictNode]:
        """Returns a list of all conflicts with 'open' status."""
        items = [c for c in self._by_id.values() if c.status == ConflictStatus.open]
        return items[:limit] if limit is not None else items

    def _row_for_upsert(self, node: ConflictNode) -> Dict[str, Any]:
        """Prepares a conflict node for a Cypher MERGE query."""
        props = node.model_dump()
        cid = node.conflict_id
        # Ensure graph properties are compatible with Cypher.
        props = {k: v for k, v in props.items() if v is not None}
        return {"id": cid, "props": props}

    async def _persist_rows(self, rows: List[Dict[str, Any]]) -> None:
        """Writes conflict data to Neo4j using an idempotent MERGE operation."""
        if not rows:
            return
        await cypher_query(
            """
            UNWIND $rows AS row
            MERGE (c:Conflict { conflict_id: row.id })
            SET c += row.props, c.updated_at = datetime()
            """, # 
            {"rows": rows},
        )