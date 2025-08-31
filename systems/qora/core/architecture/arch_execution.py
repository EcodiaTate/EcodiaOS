# systems/qora/arch_execution.py
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import time
from typing import Any

from core.utils.neo.cypher_query import cypher_query


def _uid(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=16).hexdigest()


# --- Search ------------------------------------------------------------
async def arch_search(
    query: str,
    top_k: int = 5,
    safety_max: int | None = 2,
    system: str | None = None,
) -> list[dict[str, Any]]:
    """
    Basic hybrid search; prefers tools with proper tool_* fields.
    """
    cy = """
    CALL {
      WITH $q as q
      MATCH (fn:SystemFunction)
      WHERE (fn.tool_name) IS NOT NULL
        AND ( $safety_max IS NULL OR coalesce(fn.safety_tier, 3) <= $safety_max )
        AND ( $system IS NULL OR fn.system = $system )
      WITH fn,
           // naive text score: title+desc contains query
           ( (CASE WHEN toLower(coalesce(fn.tool_name,''))     CONTAINS toLower(q) THEN 2 ELSE 0 END) +
             (CASE WHEN toLower(coalesce(fn.tool_desc,''))     CONTAINS toLower(q) THEN 1 ELSE 0 END) +
             (CASE WHEN toLower(coalesce(fn.docstring,''))     CONTAINS toLower(q) THEN 1 ELSE 0 END)
           ) AS text_score
      RETURN fn, text_score
      ORDER BY text_score DESC
      LIMIT $top_k
    }
    RETURN fn.uid AS uid,
           fn.tool_name AS name,
           coalesce(fn.tool_desc, fn.docstring, "") AS description,
           coalesce(fn.safety_tier, 3) AS safety_tier,
           coalesce(fn.allow_external, false) AS allow_external,
           coalesce(fn.tool_agent, "*") AS agent,
           coalesce(fn.tool_caps, []) AS capabilities,
           coalesce(fn.module,"") AS module,
           coalesce(fn.qualname,"") AS qualname
    """
    rows = await cypher_query(
        cy,
        {"q": query, "top_k": top_k, "safety_max": safety_max, "system": system},
    )
    return rows or []


# --- Schema ------------------------------------------------------------
async def arch_fetch_schema(uid: str) -> dict[str, Any] | None:
    cy = """
    MATCH (fn:SystemFunction {uid:$uid})
    RETURN coalesce(fn.tool_params_schema, {}) AS parameters_schema,
           coalesce(fn.tool_outputs_schema, {}) AS outputs_schema,
           coalesce(fn.safety_tier, 3) AS safety_tier,
           coalesce(fn.allow_external, false) AS allow_external,
           coalesce(fn.module,"") AS module,
           coalesce(fn.qualname,"") AS qualname
    """
    rows = await cypher_query(cy, {"uid": uid})
    return rows[0] if rows else None


# --- Exec --------------------------------------------------------------
async def arch_execute_by_uid(
    uid: str,
    args: dict[str, Any],
    caller: str | None,
    log: bool,
) -> tuple[bool, dict[str, Any]]:
    meta = await arch_fetch_schema(uid)
    if not meta:
        return False, {"error": f"Unknown uid {uid}"}

    # policy gates
    if int(meta.get("safety_tier", 3)) > 3:
        return False, {
            "error": f"Tool safety_tier too high for default execution: {meta.get('safety_tier')}",
        }
    if not meta.get("allow_external", False) and _args_imply_external(args):
        return False, {"error": "External access not permitted for this tool"}

    module = meta.get("module") or ""
    qual = meta.get("qualname") or ""
    if not module or not qual:
        return False, {"error": "Tool missing module/qualname for dispatch"}

    t0 = time.perf_counter()
    try:
        mod = importlib.import_module(module)
        fn = _resolve_qualname(mod, qual)
        result = await _maybe_await(fn(**args))
        ok = True
    except Exception as e:
        ok = False
        result = {"error": f"Execution error: {e}"}
    dt_ms = int((time.perf_counter() - t0) * 1000)

    if log:
        await _log_tool_run(uid, caller or "unknown", args, ok, dt_ms, result if not ok else None)

    payload = {"result": result, "duration_ms": dt_ms, "uid": uid}
    return ok, payload


def _args_imply_external(args: dict[str, Any]) -> bool:
    # Simple heuristic; refine as needed
    s = json.dumps(args, ensure_ascii=False)
    return any(k in s.lower() for k in ("http://", "https://", "ssh://"))


def _resolve_qualname(module, qualname: str):
    obj = module
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x


async def _log_tool_run(
    uid: str,
    caller: str,
    args: dict[str, Any],
    ok: bool,
    dt_ms: int,
    error: dict[str, Any] | None,
):
    cy = """
    MERGE (fn:SystemFunction {uid:$uid})
    CREATE (r:ToolRun {
      caller:$caller, ok:$ok, duration_ms:$dt_ms,
      args_json:$args_json, error_json:$error_json, ts:timestamp()
    })
    MERGE (r)-[:RAN]->(fn)
    """
    await cypher_query(
        cy,
        {
            "uid": uid,
            "caller": caller,
            "ok": ok,
            "dt_ms": dt_ms,
            "args_json": args,
            "error_json": error or {},
        },
    )
