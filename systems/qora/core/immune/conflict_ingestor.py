from __future__ import annotations

import hashlib
import inspect
import os
import time
from collections import OrderedDict
from contextlib import nullcontext
from typing import Any, Dict

from core.utils.neo.cypher_query import cypher_query


# ---------- immune_section wrapper ----------
def _get_immune_cm(tag: str = ""):
    try:
        from systems.qora.core.immune.auto_instrument import immune_section as _immune

        try:
            return _immune(tag)
        except TypeError:
            return _immune()
    except Exception:
        return nullcontext()


def _is_async_cm(cm) -> bool:
    aenter = getattr(cm, "__aenter__", None)
    aexit = getattr(cm, "__aexit__", None)
    return inspect.iscoroutinefunction(aenter) or inspect.iscoroutinefunction(aexit)


EVIDENCE_BYTES_MAX = 8000

# Console log throttle for "Received conflict..." lines
_PRINT_TTL = float(os.getenv("CONFLICT_INGESTOR_PRINT_TTL_SEC", "15"))
_LAST_PRINT_BY_ID: dict[str, float] = {}
_PRINT_TTL_SEC = float(os.getenv("CONFLICT_INGESTOR_PRINT_TTL_SEC", "15"))
_LAST_PRINT: OrderedDict[str, float] = OrderedDict()


def _should_print_once(conflict_id: str) -> bool:
    now = time.monotonic()
    last = _LAST_PRINT.get(conflict_id)
    if last is not None and (now - last) < _PRINT_TTL_SEC:
        return False
    if conflict_id in _LAST_PRINT:
        _LAST_PRINT.move_to_end(conflict_id)
    _LAST_PRINT[conflict_id] = now
    while len(_LAST_PRINT) > 2048:
        _LAST_PRINT.popitem(last=False)
    return True


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_severity(s: Any) -> str:
    s = str(s or "medium").lower()
    return s if s in {"low", "medium", "high", "critical"} else "medium"


def _conflict_id_from(payload: dict[str, Any], stack_blob: str) -> str:
    sig = payload.get("signature")
    if isinstance(sig, str) and sig:
        return sig
    return hashlib.sha256(stack_blob.encode("utf-8", "replace")).hexdigest()


async def on_conflict_detected(payload: dict[str, Any]) -> None:
    """
    Listener for 'conflict_detected' events published by ConflictSDK.
    Idempotent upsert in Neo4j; prints are rate-limited per conflict_id.
    """
    stack_blob = payload.get("stack_blob") or ""
    if not isinstance(stack_blob, str):
        stack_blob = str(stack_blob)
    conflict_id = _conflict_id_from(payload, stack_blob)

    now = time.time()
    last = _LAST_PRINT_BY_ID.get(conflict_id, 0)
    if (now - last) >= _PRINT_TTL:
        component = payload.get("component") or payload.get("system") or "unknown"
        sev = _normalize_severity(payload.get("severity"))
        if _should_print_once(conflict_id):
            print(
                f"[Conflict Ingestor] Received conflict id={conflict_id} component={component} severity={sev}",
            )
        _LAST_PRINT_BY_ID[conflict_id] = now

    cm = _get_immune_cm("conflict_ingestor")
    if _is_async_cm(cm):
        async with cm:
            await _ingest(payload, conflict_id, stack_blob)
    else:
        with cm:
            await _ingest(payload, conflict_id, stack_blob)


async def _ingest(payload: dict[str, Any], conflict_id: str, stack_blob: str) -> None:
    try:
        ev_sha = hashlib.sha256(stack_blob.encode("utf-8", "replace")).hexdigest()
        ev_bytes = stack_blob[:EVIDENCE_BYTES_MAX]
        t = _now_ms()

        description = (payload.get("description") or "")[:1024]
        version = (payload.get("version") or "")[:128]
        severity = _normalize_severity(payload.get("severity"))
        etype = (payload.get("etype") or "")[:128]
        component = payload.get("component") or payload.get("system") or "unknown"
        origin = payload.get("signature") or payload.get("origin_id") or conflict_id

        extra_ctx = payload.get("context") or {}
        if not isinstance(extra_ctx, dict):
            extra_ctx = {}
        extra_ctx = {"source_system": payload.get("source_system") or "synk", **extra_ctx}

        await cypher_query(
            """
            UNWIND [$row] AS row
            MERGE (c:Conflict { conflict_id: row.c.conflict_id })
            ON CREATE SET
              c.system      = row.c.system,
              c.description = row.c.description,
              c.version     = row.c.version,
              c.severity    = row.c.severity,
              c.etype       = row.c.etype,
              c.origin      = row.c.origin,
              c.created_at  = row.t,
              c.last_seen   = row.t,
              c.seen_count  = 1,
              c += row.c.extra
            ON MATCH SET
              c.last_seen   = row.t,
              c.seen_count  = coalesce(c.seen_count, 0) + 1

            MERGE (e:Evidence { sha: row.e.sha })
            ON CREATE SET
              e.type  = row.e.type,
              e.bytes = row.e.bytes,
              e.t     = row.t
            ON MATCH SET
              e.type  = coalesce(e.type, row.e.type)

            MERGE (c)-[r:HAS_EVIDENCE]->(e)
            ON CREATE SET r.t = row.t, r.source = 'synk'
            """,
            {
                "row": {
                    "t": t,
                    "c": {
                        "conflict_id": conflict_id,
                        "system": component,
                        "description": description,
                        "version": version,
                        "severity": severity,
                        "etype": etype,
                        "origin": origin,
                        "extra": extra_ctx,
                    },
                    "e": {"sha": ev_sha, "type": "stack", "bytes": ev_bytes},
                },
            },
        )
    except Exception as e:
        print(f"!!! CRITICAL: Failed to write conflict to graph: {e}")
