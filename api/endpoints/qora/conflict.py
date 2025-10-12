from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

try:
    from core.utils.neo.cypher_query import cypher_query
except Exception as _e:
    cypher_query = None
    _cypher_import_err = _e

conflicts_router = APIRouter(tags=["qora", "conflicts"])


def _hash_sig(sig: str) -> str:
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()


async def _maybe_await(x):
    if callable(x):
        x = x()
    if hasattr(x, "__await__"):
        return await x
    return x


class CreateConflictReq(BaseModel):
    # Accept either canonical "conflict_id" or legacy "signature"
    conflict_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("conflict_id", "signature"),
        description="Deterministic conflict id; if legacy signature is provided instead, we sha1 it.",
    )
    system: str = Field(default="unknown", description="Originating subsystem")
    description: str = Field(default="")
    context: dict[str, Any] = Field(default_factory=dict)


@conflicts_router.post("/create", response_model=dict)
async def create_conflict(req: CreateConflictReq) -> dict:
    if cypher_query is None:
        raise HTTPException(
            status_code=500,
            detail=f"cypher_query_unavailable[{_cypher_import_err.__class__.__name__}]: {_cypher_import_err!s}",
        )

    raw = req.model_dump(by_alias=False)
    cid = (raw.get("conflict_id") or "").strip()
    if not cid:
        # With AliasChoices, legacy 'signature' also lands in conflict_id here.
        sig = (raw.get("conflict_id") or "").strip()
        if not sig:
            raise HTTPException(status_code=422, detail="conflict_id or signature is required")
        cid = _hash_sig(sig)

    # Neo4j props must be primitives/arrays; store JSON string
    ctx_json = json.dumps(req.context or {}, ensure_ascii=False)

    q = """
    MERGE (c:Conflict {conflict_id: $conflict_id})
      ON CREATE SET c.created_at = timestamp(),
                    c.first_system = $system,
                    c.description = $description
      ON MATCH SET  c.updated_at = timestamp()
    SET c.last_context_json = $context_json,
        c.last_system       = $system
    RETURN c.conflict_id AS conflict_id
    """

    params = {
        "conflict_id": cid,
        "system": (req.system or "unknown").strip() or "unknown",
        "description": req.description or "",
        "context_json": ctx_json,
    }

    try:
        rows = await _maybe_await(lambda: cypher_query(q, params))
        if isinstance(rows, list) and rows:
            return {"ok": True, "conflict_id": rows[0].get("conflict_id", cid)}
        if isinstance(rows, dict) and "conflict_id" in rows:
            return {"ok": True, "conflict_id": rows["conflict_id"]}
        return {"ok": True, "conflict_id": cid}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"conflict_upsert_error[{e.__class__.__name__}]: {e!s}",
        )
