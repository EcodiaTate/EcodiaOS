from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from systems.synk.core.tools.neo import (
    create_conflict_node,
    add_relationship,
    add_node,
)

conflicts_router = APIRouter(tags=["qora"])


class ConflictCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    system: str
    description: str
    signature: str  # A hash or key identifying the failure context
    context: dict[str, Any] = Field(default_factory=dict)


class ConflictResolve(BaseModel):
    model_config = ConfigDict(extra="ignore")
    successful_diff: str


def _jsonify(obj: Any) -> Any:
    # Make Neo4j values (including neo4j.time.DateTime) JSON-safe.
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_jsonify(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _jsonify(v) for k, v in obj.items()}
    # Try neo4j DateTime → native isoformat
    try:
        from neo4j.time import DateTime  # type: ignore
        if isinstance(obj, DateTime):
            try:
                return obj.to_native().isoformat()
            except Exception:
                return str(obj)
    except Exception:
        pass
    # Fallback: stringify anything unknown
    return str(obj)


@conflicts_router.post("/create")
async def log_conflict(req: ConflictCreate) -> dict[str, Any]:
    """Logs a new, unresolved conflict to the graph."""
    try:
        node = await create_conflict_node(
            system=req.system,
            description=req.description,
            origin_node_id=req.signature,
            additional_data=req.context,
        )
        if not isinstance(node, dict):
            raise RuntimeError(f"Unexpected node shape: {type(node)!r}")

        # 🔒 Sanitize to primitives (avoid neo4j.time.DateTime in response)
        props = (node.get("properties") or {}) if isinstance(node, dict) else {}
        uuid = node.get("uuid") or props.get("uuid") or req.signature
        created_at = props.get("created_at")
        created_at_str = str(created_at) if created_at is not None else None

        return {"ok": True, "uuid": uuid, "created_at": created_at_str}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create conflict node: {e!r}")


@conflicts_router.post("/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: str, req: ConflictResolve) -> dict[str, Any]:
    """Links a successful solution to a previously logged conflict."""
    try:
        solution_node = await add_node(
            labels=["Solution"],
            properties={"diff": req.successful_diff, "resolves_conflict": conflict_id},
        )
        if not isinstance(solution_node, dict):
            raise RuntimeError(f"Unexpected solution_node shape: {type(solution_node)!r}")

        solution_id = (solution_node.get("properties", {}) or {}).get("uuid") or solution_node.get("uuid")
        if not solution_id:
            raise RuntimeError("Solution node did not return a 'uuid'")

        await add_relationship(
            src_match={"label": "Conflict", "match": {"uuid": conflict_id}},
            dst_match={"label": "Solution", "match": {"uuid": solution_id}},
            rel_type="RESOLVED_BY",
        )
        return {"ok": True, "message": f"Conflict {conflict_id} marked as resolved by solution {solution_id}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve conflict: {e!r}")
