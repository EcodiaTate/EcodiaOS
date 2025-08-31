# api/endpoints/switchboard/flags.py
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from core.utils.neo.cypher_query import cypher_query  # ✅ driverless Neo

router = APIRouter(prefix="/switchboard")


class FlagUpsert(BaseModel):
    # Accept extra keys from forwarders without failing validation
    model_config = ConfigDict(extra="ignore")

    key: str = Field(..., description="Flag key (unique)")
    type: str = Field(..., description="Storage type hint, e.g., 'json', 'str', 'int'")
    value: Any = Field(..., description="Arbitrary JSON-serializable value")
    reason: str | None = Field(default=None, description="Why the value changed")
    description: str | None = Field(default=None, description="Human-readable flag description")
    component: str | None = Field(default=None, description="Optional component to link flag to")


class FlagOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    type: str = "json"
    value: Any
    updated_at: int
    description: str | None = None


def _to_json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


def _from_json(s: Any) -> Any:
    import json
    if isinstance(s, (dict, list, int, float, bool)) or s is None:
        return s
    try:
        return json.loads(s)
    except Exception:
        return s


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _actor_identity() -> str:
    # Identity comes from ENV now (no config import)
    return os.getenv("IDENTITY_ID", "ecodia.system")


@router.get("/flags", response_model=list[FlagOut])
async def list_flags(prefix: str | None = None):
    cy = (
        "MATCH (f:Flag) "
        + ("WHERE f.key STARTS WITH $p " if prefix else "")
        + "RETURN f.key AS key, f.type AS type, "
        "coalesce(properties(f)['value_json'], properties(f)['default_json'], 'null') AS value_json, "
        "coalesce(f.updated_at,0) AS updated_at, f.description AS description "
        "ORDER BY key"
    )
    params: dict[str, Any] = {"p": prefix} if prefix else {}
    recs = await cypher_query(cy, params)

    out: list[FlagOut] = []
    for r in recs or []:
        out.append(
            FlagOut(
                key=r.get("key"),
                type=r.get("type") or "json",
                value=_from_json(r.get("value_json", "null")),
                updated_at=int(r.get("updated_at") or 0),
                description=r.get("description"),
            ),
        )
    return out


@router.get("/flags/{key}", response_model=FlagOut)
async def get_flag(key: str):
    recs = await cypher_query(
        "MATCH (f:Flag {key:$k}) "
        "RETURN f.key AS key, f.type AS type, "
        "coalesce(properties(f)['value_json'], properties(f)['default_json'], 'null') AS value_json, "
        "coalesce(f.updated_at,0) AS updated_at, f.description AS description",
        {"k": key},
    )
    if not recs:
        raise HTTPException(status_code=404, detail=f"Flag {key} not found")

    r = recs[0]
    return FlagOut(
        key=r.get("key"),
        type=r.get("type") or "json",
        value=_from_json(r.get("value_json", "null")),
        updated_at=int(r.get("updated_at") or 0),
        description=r.get("description"),
    )


@router.put("/flags", response_model=FlagOut)
async def set_flag(body: FlagUpsert):
    now_ms = _now_ms()
    actor = _actor_identity()

    # read old (if any) using projection
    recs = await cypher_query(
        "MATCH (f:Flag {key:$k}) RETURN f.value_json AS value_json",
        {"k": body.key},
    )
    old_json = (recs and recs[0].get("value_json")) or None

    # upsert + audit trail
    cy = """
    MERGE (f:Flag {key:$k})
      ON CREATE SET
        f.type = $t,
        f.default_json = coalesce(f.default_json, $v),
        f.description = $d,
        f.state = 'active'
      ON MATCH SET
        f.type = coalesce(f.type, $t),
        f.description = coalesce($d, f.description)
    SET f.value_json = $v, f.updated_at = $now

    WITH f
    MERGE (i:Identity {key:$actor})
      ON CREATE SET i.created_at = $now

    MERGE (chg:FlagChange {id:$id})
      ON CREATE SET
        chg.key = $k,
        chg.old_json = $old,
        chg.new_json = $v,
        chg.actor = $actor,
        chg.reason = $reason,
        chg.ts = $now

    MERGE (chg)-[:CHANGED_FLAG]->(f)
    MERGE (chg)-[:BY]->(i)
    """
    await cypher_query(
        cy,
        {
            "k": body.key,
            "t": body.type,
            "v": _to_json(body.value),
            "d": body.description,
            "now": now_ms,
            "id": str(uuid4()),
            "old": old_json,
            "actor": actor,
            "reason": body.reason,
        },
    )

    # optional component link
    if body.component:
        await cypher_query(
            """
            MATCH (f:Flag {key:$k})
            MERGE (c:Component {name:$c})
            MERGE (f)-[:FOR_COMPONENT]->(c)
            """,
            {"k": body.key, "c": body.component},
        )

    # return fresh read
    return await get_flag(body.key)
