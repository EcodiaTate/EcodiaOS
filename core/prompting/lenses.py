# core/prompting/lenses.py
from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any, Dict, List, Optional

from core.llm.embeddings_gemini import get_embedding

_log = logging.getLogger("ecodia.lenses")

from core.utils.neo.cypher_query import cypher_query  # async graph access
from systems.synk.core.tools.neo import semantic_graph_search  # semantic retrieval

# ---------------------------------------------------------------------------
# == NEW: IDENTITY FACET LENSES
# ---------------------------------------------------------------------------


async def _query_facets_by_category(category: str) -> dict[str, Any]:
    """
    Query all active, versioned facets for a specific category.
    Returns { "<category>_facets": [ {name, text, version}, ... ] }
    """
    context_key = f"{category}_facets"
    if cypher_query is None:
        return {context_key: []}

    q = """
    MATCH (f:Facet {category: $category})
    WITH f.name AS name, max(f.version) AS latest_version
    MATCH (latest_facet:Facet {name: name, version: latest_version, category: $category})
    RETURN
        latest_facet.name   AS name,
        latest_facet.text   AS text,
        latest_facet.version AS version
    """
    try:
        rows = await cypher_query(q, {"category": category})
        facets = [
            {"name": r.get("name"), "text": r.get("text"), "version": r.get("version")}
            for r in (rows or [])
        ]
        return {context_key: facets}
    except Exception as e:
        _log.warning(f"[lens_facets] Failed to query for category '{category}': {e}")
        return {context_key: []}


async def lens_affective_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("affective")


async def lens_ethical_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("ethical")


async def lens_safety_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("safety")


async def lens_mission_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("mission")


async def lens_style_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("style")


async def lens_voice_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("voice")


# +++ START ADDITION: Missing Facet Lenses +++
async def lens_philosophical_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("philosophical")


async def lens_epistemic_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("epistemic_humility")


async def lens_operational_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("operational")


async def lens_compliance_facets(_: Any) -> dict[str, Any]:
    return await _query_facets_by_category("compliance")


# +++ END ADDITION +++


# ---------------------------------------------------------------------------
# == EXISTING LENSES
# ---------------------------------------------------------------------------


async def lens_equor_identity(agent_name: str) -> dict[str, Any]:
    """
    Pulls basic identity facets for an agent from the graph.
    Falls back to returning just the agent_name if graph is unavailable.
    Returns:
    {
      "equor": {
        "identity": {
          "agent_name": str,
          "identity_text": str,
          "facets": list[str]
        }
      }
    }
    """
    fallback = {
        "equor": {
            "identity": {
                "agent_name": agent_name,
                "identity_text": f"Agent Name: {agent_name}",
                "facets": [],
            },
        },
    }

    if cypher_query is None:
        return fallback

    q = """
    MATCH (a:Agent {name: $name})
    OPTIONAL MATCH (a)-[:HAS_FACET]->(f:Facet)
    RETURN a.summary AS summary, a.purpose AS purpose, collect(f.name) AS facets
    """
    try:
        rows = await cypher_query(q, {"name": agent_name})
    except Exception as e:
        _log.warning(f"[lens_equor_identity] cypher failed: {e}")
        return fallback

    if not rows:
        return fallback

    r = rows[0]
    parts: list[str] = []
    summary = r.get("summary")
    purpose = r.get("purpose")
    facets = r.get("facets") or []

    if summary:
        parts.append(str(summary).strip())
    if purpose:
        parts.append(f"Purpose: {str(purpose).strip()}")
    if facets:
        parts.append("Facets: " + ", ".join([str(x) for x in facets if x]))

    return {
        "equor": {
            "identity": {
                "agent_name": agent_name,
                "identity_text": "\n".join(parts),
                "facets": facets,
            },
        },
    }


async def lens_atune_salience(salience: dict[str, Any] | None) -> dict[str, Any]:
    """Pass-through for salience dicts."""
    return {"salience": salience or {}}


async def lens_affect(affect: dict[str, Any] | None) -> dict[str, Any]:
    """Pass-through for affect dicts, e.g., {'curiosity': 0.6}."""
    return {"affect": affect or {}}


async def lens_event_canonical(event: dict[str, Any] | None) -> dict[str, Any]:
    """Pass-through for canonical event objects."""
    return {"event": event or {}}


async def lens_retrieval_semantic(query: str, limit: int = 6) -> dict[str, Any]:
    """
    Semantic retrieval lens via systems.synk if available.
    Returns: {"retrieval": [ ...items... ]}
    """
    if not semantic_graph_search:
        return {"retrieval": []}
    try:
        items = await semantic_graph_search(query_text=query, top_k=limit)
    except Exception as e:
        _log.warning(f"[lens_retrieval_semantic] search failed: {e}")
        items = []
    return {"retrieval": items or []}


async def lens_ecodia_self_concept(_: Any) -> dict[str, Any]:
    """
    Pulls the current, active EcodiaCoreIdentity from the graph.
    This represents the system's synthesized self-concept.
    """
    default_identity = {
        "ecodia": {
            "self_concept": {
                "version": 0,
                "narrative_summary": "EcodiaOS is a helpful assistant.",
                "core_directives": ["Be helpful.", "Be harmless."],
                "is_fallback": True,
            },
        },
    }
    if cypher_query is None:
        return default_identity

    q = """
    MATCH (core:EcodiaCoreIdentity)
    WHERE NOT (core)-[:SUPERSEDED_BY]->()
    RETURN
        core.version AS version,
        core.narrative_summary AS narrative_summary,
        core.core_directives AS core_directives,
        core.current_stance AS current_stance
    ORDER BY core.version DESC
    LIMIT 1
    """
    try:
        rows = await cypher_query(q)
        if not rows:
            return default_identity

        data = rows[0]
        return {
            "ecodia": {
                "self_concept": {
                    "version": data.get("version"),
                    "narrative_summary": data.get("narrative_summary"),
                    "core_directives": data.get("core_directives") or [],
                    "current_stance": data.get("current_stance") or {},
                    "is_fallback": False,
                },
            },
        }
    except Exception as e:
        _log.warning(f"[lens.ecodia_self_concept] failed to query graph: {e}")
        return default_identity


async def lens_tools_catalog(input_obj: Any) -> dict[str, Any]:
    """
    Looks up PROBE endpoints from the graph using a direct Cypher query.
    """
    query_text = ""
    if isinstance(input_obj, dict):
        query_text = (
            input_obj.get("retrieval_query")
            or input_obj.get("goal")
            or input_obj.get("user_text")
            or input_obj.get("text")
            or ""
        ) or ""
    elif isinstance(input_obj, str):
        query_text = input_obj or ""

    if cypher_query is None:
        _log.warning("[lens.tools_catalog] cypher_query is unavailable. Cannot search for tools.")
        return {"tools_catalog": {"candidates": []}}

    # This is now the only path for tool discovery.
    q = """
    MATCH (e:VoxisTool)
    WHERE e.mode = 'probe'
    RETURN
      e.driver_name       AS driver_name,
      e.endpoint          AS endpoint,
      e.mode              AS mode,
      e.title             AS title,
      e.description       AS description,
      e.arg_schema_json   AS arg_schema_json,
      e.defaults_json     AS defaults_json,
      e.tags              AS tags,
      0.5                 AS score
    LIMIT 15
    """
    try:
        rows = await cypher_query(q, {"q": query_text})
        out: list[dict[str, Any]] = []
        for r in rows or []:
            try:
                arg_schema = json.loads(r.get("arg_schema_json") or "{}")
            except Exception:
                arg_schema = {}
            try:
                _defaults = json.loads(r.get("defaults_json") or "{}")
            except Exception:
                _defaults = {}

            driver_name = (r.get("driver_name") or "").strip()
            endpoint = (r.get("endpoint") or r.get("mode") or "probe").strip()
            func_name = f"{driver_name}.{endpoint}"

            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "description": (r.get("description") or r.get("title") or "").strip(),
                        "parameters": arg_schema,
                    },
                    "_meta": {
                        "driver_name": driver_name,
                        "endpoint": endpoint,
                        "mode": r.get("mode") or "probe",
                        "tags": r.get("tags") or [],
                        "defaults": _defaults,
                        "score": float(r.get("score") or 0.0),
                    },
                },
            )

        return {"tools_catalog": {"candidates": out}}
    except Exception:
        return {"tools_catalog": {"candidates": []}}


# --- Simula lenses ------------------------------------------------------------

# Logger
_log = logging.getLogger(__name__)

# Optional imports (degrade gracefully in unit tests / offline)
try:
    from core.llm.embeddings_gemini import get_embedding
except Exception:  # pragma: no cover

    async def get_embedding(_: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
        _log.warning("[lenses] get_embedding unavailable; returning zero vector.")
        return [0.0] * 768  # safe default


# ──────────────────────────────────────────────────────────────────────────────
# Tool Catalog (lens_get_tools)
# ──────────────────────────────────────────────────────────────────────────────


def _row_to_candidate(r: dict[str, Any]) -> dict[str, Any]:
    """Transforms a Cypher row into a tools-catalog candidate."""
    pgm = r.get("pgm_raw")
    if isinstance(pgm, str):
        try:
            pgm = json.loads(pgm)
        except Exception:
            pgm = {}
    elif not isinstance(pgm, dict):
        pgm = {}

    tool_name = pgm.get("tool_name") or r.get("name") or r.get("arm_id") or "unknown_tool"

    description = r.get("description")
    if isinstance(description, str):
        description = description.strip()
    else:
        description = f"Simula tool: {tool_name}"

    params_schema = (
        pgm.get("parameters_schema") or r.get("parameters") or {"type": "object", "properties": {}}
    )

    tool_modes = pgm.get("tool_modes") or r.get("tool_modes") or []

    try:
        score_val = float(r.get("score", 0.5))
    except (TypeError, ValueError):
        score_val = 0.5

    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description,
            "parameters": params_schema,
        },
        "_meta": {
            "arm_id": r.get("arm_id"),
            "modes": tool_modes,
            "score": score_val,
        },
    }


async def _lens_get_tools_impl(
    *,
    query_text: str | None,
    modes: list[str] | None,
    top_k: int,
) -> dict[str, Any]:
    if cypher_query is None:
        _log.warning("[lens_get_tools] cypher_query unavailable.")
        return {"tools_catalog": {"candidates": []}}

    params: dict[str, Any] = {"k": int(top_k)}
    where_clauses: list[str] = ["a.family_id = 'simula.agent.tools'"]

    if modes:
        mode_tags = [f"mode::{m}" for m in modes]
        params["mode_tags"] = mode_tags

    try:
        if query_text:
            _log.info("[lens_get_tools] KNN + mode filter q='%s...'", (query_text or "")[:100])
            emb = await get_embedding(query_text, task_type="RETRIEVAL_QUERY")
            params["embedding"] = emb

            match_clause = """
CALL db.index.vector.queryNodes('policyArmIndex', $k, $embedding)
YIELD node AS a, score
"""
            if modes:
                where_clauses.append("size([t IN coalesce(a.tags, []) WHERE t IN $mode_tags]) > 0")

            final_query = f"""
{match_clause}
WHERE {' AND '.join(where_clauses)}
RETURN
  a.id                  AS arm_id,
  a.description         AS description,
  coalesce(a.tags, [])  AS tool_modes,
  a.policy_graph_meta   AS pgm_raw,
  score
ORDER BY score DESC
LIMIT $k
"""
        else:
            default_score = 0.5
            match_clause = "MATCH (a:PolicyArm)"
            score_with = f"WITH a, {default_score} AS score"

            if modes:
                _log.info("[lens_get_tools] mode-only filter: %s", modes)
                where_clauses.append("size([t IN coalesce(a.tags, []) WHERE t IN $mode_tags]) > 0")
            else:
                _log.info("[lens_get_tools] fallback to general tools")
                where_clauses.append("'mode::general' IN coalesce(a.tags, [])")

            final_query = f"""
{match_clause}
WHERE {' AND '.join(where_clauses)}
{score_with}
RETURN
  a.id                  AS arm_id,
  a.description         AS description,
  coalesce(a.tags, [])  AS tool_modes,
  a.policy_graph_meta   AS pgm_raw,
  score
ORDER BY score DESC
LIMIT $k
"""

        rows = await cypher_query(final_query, params)
        parsed: list[dict[str, Any]] = []
        for r in rows or []:
            c = _row_to_candidate(r)
            if c["function"]["name"] and c["function"]["name"] != "unknown_tool":
                parsed.append(c)
        _log.info("[lens_get_tools] candidates=%d", len(parsed))
        return {"tools_catalog": {"candidates": parsed}}
    except Exception as e:
        _log.exception("[lens_get_tools] failed: %r", e)
        return {"tools_catalog": {"candidates": []}}


async def lens_get_tools(ctx: Any) -> dict[str, Any]:
    """
    PUBLIC lens called by build_prompt() with a single positional context.
    Extracts query text / modes / k from the context and delegates to _lens_get_tools_impl.
    """
    query_text: str | None = None
    modes: list[str] = []
    top_k: int = 15

    if isinstance(ctx, dict):
        query_text = (
            ctx.get("retrieval_query")
            or ctx.get("goal")
            or ctx.get("user_text")
            or ctx.get("text")
            or None
        )
        if "allowed_modes" in ctx and isinstance(ctx["allowed_modes"], list):
            modes = [str(m) for m in ctx["allowed_modes"] if m]
        elif "mode" in ctx and isinstance(ctx["mode"], str):
            modes = [ctx["mode"]]
        try:
            top_k = int(ctx.get("k", top_k))
        except Exception:
            pass
    elif isinstance(ctx, str):
        query_text = ctx or None

    return await _lens_get_tools_impl(query_text=query_text, modes=modes or None, top_k=top_k)


# ──────────────────────────────────────────────────────────────────────────────
# Advice retrieval (pre/post plan)
# ──────────────────────────────────────────────────────────────────────────────

# Tunables
_ADVICE_TOPK_QUERY = 24  # pull more from KNN, then filter down
_ADVICE_MAX_INJECT = 6  # hard cap injected items
_ADVICE_QUOTAS = {3: 2, 2: 3, 1: 1}  # per-level caps: T3, T2, T1
_ADVICE_TOKEN_BUDGET = 1200  # soft token cap for rendered block


async def _embed_query_vec(q: str | Sequence[str]) -> list[float]:
    """
    Embed a single query string or multiple query hints (mean-pooled).
    Uses RETRIEVAL_QUERY mode for best search performance.
    """
    if isinstance(q, str):
        return await get_embedding(q, task_type="RETRIEVAL_QUERY")

    vecs: list[list[float]] = []
    for part in q:
        if not part:
            continue
        vecs.append(await get_embedding(part, task_type="RETRIEVAL_QUERY"))
    if not vecs:
        return await get_embedding("", task_type="RETRIEVAL_QUERY")

    dim = len(vecs[0])
    acc = [0.0] * dim
    for v in vecs:
        if len(v) != dim:
            raise RuntimeError(
                f"[lens_simula_advice] query embedding dims mismatch: {len(v)} != {dim}",
            )
        for i in range(dim):
            acc[i] += v[i]
    n = float(len(vecs))
    return [x / n for x in acc]


def _advice_proximity(scope: list[str], target_fqname: str | None) -> float:
    """Boost items that touch the exact symbol/module."""
    if not scope:
        return 1.0
    tf = (target_fqname or "").strip()
    if not tf:
        return 1.0
    joined = " ".join(scope)
    if tf and tf in joined:
        return 1.2
    tf_mod = tf.split("::")[0]
    if tf_mod and tf_mod in joined:
        return 1.1
    return 1.0


def _advice_recency_bonus(last_seen_ms: int | None) -> float:
    """Light recency bump; robust to missing data."""
    try:
        if not last_seen_ms:
            return 1.0
        import time

        days = max(0.0, (time.time() * 1000.0 - float(last_seen_ms)) / (1000.0 * 60 * 60 * 24))
        return 1.0 + min(0.2, 0.02 * (1.0 / (1.0 + days)))
    except Exception:
        return 1.0


def _sanitize_advice_item(node_row: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields the partial needs and ensure list types."""

    def as_list(x):
        return x if isinstance(x, list) else []

    return {
        "id": node_row.get("id"),
        "level": int(node_row.get("level") or 1),
        "text": node_row.get("text") or "",
        "checklist": as_list(node_row.get("checklist")),
        "donts": as_list(node_row.get("donts")),
        "validation": as_list(node_row.get("validation")),
        "scope": as_list(node_row.get("scope")),
        "weight": float(node_row.get("weight") or 1.0),
        "thr": float(node_row.get("thr") or 0.84),
        "score": float(node_row.get("score") or 0.0),
        "last_seen": node_row.get("last_seen"),
    }


async def _knn_advice(qtext_or_hints: str | Sequence[str], k: int) -> list[dict[str, Any]]:
    if cypher_query is None:
        _log.warning("[lens_simula_advice] cypher_query unavailable; returning no advice.")
        return []
    try:
        emb = await _embed_query_vec(qtext_or_hints)
        rows = await cypher_query(
            """
            CALL db.index.vector.queryNodes('advice_embedding_idx', $k, $emb)
            YIELD node, score
            WITH node, score, keys(node) AS ks
            RETURN
              node.id AS id,
              CASE WHEN 'level'         IN ks THEN node['level']         ELSE 1 END      AS level,
              CASE WHEN 'text'          IN ks THEN node['text']          ELSE '' END     AS text,
              CASE WHEN 'checklist'     IN ks THEN node['checklist']     ELSE [] END     AS checklist,
              CASE WHEN 'donts'         IN ks THEN node['donts']         ELSE [] END     AS donts,
              CASE WHEN 'validation'    IN ks THEN node['validation']    ELSE [] END     AS validation,
              CASE WHEN 'scope'         IN ks THEN node['scope']         ELSE [] END     AS scope,
              CASE WHEN 'weight'        IN ks THEN node['weight']        ELSE 1.0 END    AS weight,
              CASE WHEN 'sim_threshold' IN ks THEN node['sim_threshold'] ELSE 0.0 END    AS thr,
              CASE WHEN 'last_seen'     IN ks THEN node['last_seen']     ELSE null END   AS last_seen,
              score AS score
            ORDER BY score DESC
            LIMIT $k
            """,
            {"emb": emb, "k": k},
        )
        return [_sanitize_advice_item(r) for r in (rows or [])]
    except Exception as e:
        _log.warning("[lens_simula_advice] KNN failed: %r", e)
        return []


def _blend_and_select(
    items: list[dict[str, Any]],
    *,
    target_fqname: str | None,
    max_total: int,
    quotas: dict[int, int],
) -> list[dict[str, Any]]:
    """Blend score and enforce per-level quotas + de-dup."""
    scored = []
    for it in items:
        prox = _advice_proximity(it.get("scope"), target_fqname)
        rec = _advice_recency_bonus(it.get("last_seen"))
        it["_blended"] = float(it["score"]) * float(it["weight"]) * prox * rec
        scored.append(it)
    scored.sort(key=lambda x: x["_blended"], reverse=True)

    kept: list[dict[str, Any]] = []
    used = {1: 0, 2: 0, 3: 0}
    seen_texts: list[str] = []
    for it in scored:
        lvl = int(it.get("level") or 1)
        if used.get(lvl, 0) >= quotas.get(lvl, 0):
            continue
        txt = (it.get("text") or "").strip()
        if txt and txt in seen_texts:
            continue
        kept.append(it)
        used[lvl] = used.get(lvl, 0) + 1
        seen_texts.append(txt)
        if len(kept) >= max_total:
            break
    return kept


def _build_query_from_input(input_obj: Any, *, mode: str) -> tuple[str, str | None, list[str]]:
    """
    Compose primary query + optional multi-hints.
    mode: "pre" uses goal/target/history; "post" prefers plan text if provided.
    Returns (primary_query, target_fqname, hints_list)
    """
    goal = ""
    target_fqname = None
    history = ""
    plan_text = ""
    hints: list[str] = []

    if isinstance(input_obj, dict):
        goal = (
            input_obj.get("goal") or input_obj.get("text") or input_obj.get("user_text") or ""
        ).strip()
        target_fqname = input_obj.get("target_fqname") or input_obj.get("target") or None
        history = (
            input_obj.get("history_summary") or input_obj.get("context_summary") or ""
        ).strip()
        plan = input_obj.get("initial_plan") or input_obj.get("plan_text") or ""
        if isinstance(plan, dict):
            try:
                plan_text = json.dumps(
                    {"plan": plan.get("plan", []), "interim": plan.get("interim_thought")},
                    ensure_ascii=False,
                )
            except Exception:
                plan_text = ""
        elif isinstance(plan, str):
            plan_text = plan
        raw_hints = input_obj.get("advice_query_hints")
        if isinstance(raw_hints, list):
            hints = [str(h).strip() for h in raw_hints if h]
        elif isinstance(raw_hints, str) and raw_hints.strip():
            hints = [raw_hints.strip()]
    elif isinstance(input_obj, str):
        goal = input_obj.strip()

    if mode == "post" and plan_text:
        q = f"{goal}\nTarget:{target_fqname or ''}\nPlan:\n{plan_text}"
    else:
        q = f"{goal}\nTarget:{target_fqname or ''}\nContext:\n{history}"
    return q, target_fqname, hints


async def lens_simula_advice_preplan(input_obj: Any) -> dict[str, Any]:
    """
    Semantic retrieval before planning.
    Input may include: goal, target_fqname, history_summary, advice_query_hints, k
    Output: { "advice_items": [...], "advice_meta": {...} }
    """
    q, target, hints = _build_query_from_input(input_obj, mode="pre")
    try:
        topk = (
            int(input_obj.get("k", _ADVICE_TOPK_QUERY))
            if isinstance(input_obj, dict)
            else _ADVICE_TOPK_QUERY
        )
    except Exception:
        topk = _ADVICE_TOPK_QUERY

    q_input: str | list[str] = [q] + hints if hints else q
    _log.info("[lens_simula_advice_preplan] hints=%d k=%d", len(hints), topk)

    items = await _knn_advice(q_input, topk)
    selected = _blend_and_select(
        items,
        target_fqname=target,
        max_total=_ADVICE_MAX_INJECT,
        quotas=_ADVICE_QUOTAS,
    )
    meta = {
        "queried": len(items),
        "selected": len(selected),
        "target_fqname": target,
        "token_budget": _ADVICE_TOKEN_BUDGET,
        "lens": "preplan",
        "ids": [i["id"] for i in selected],
        "hints_used": hints,
    }
    return {"advice_items": selected, "advice_meta": meta}


async def lens_simula_advice_postplan(input_obj: Any) -> dict[str, Any]:
    """
    Semantic retrieval after an initial plan exists (refines on the planned steps).
    Input may include: goal, target_fqname, initial_plan (dict|str), advice_query_hints, k
    """
    q, target, hints = _build_query_from_input(input_obj, mode="post")
    try:
        topk = (
            int(input_obj.get("k", _ADVICE_TOPK_QUERY))
            if isinstance(input_obj, dict)
            else _ADVICE_TOPK_QUERY
        )
    except Exception:
        topk = _ADVICE_TOPK_QUERY

    q_input: str | list[str] = [q] + hints if hints else q
    _log.info("[lens_simula_advice_postplan] hints=%d k=%d", len(hints), topk)

    items = await _knn_advice(q_input, topk)
    selected = _blend_and_select(
        items,
        target_fqname=target,
        max_total=_ADVICE_MAX_INJECT,
        quotas=_ADVICE_QUOTAS,
    )
    meta = {
        "queried": len(items),
        "selected": len(selected),
        "target_fqname": target,
        "token_budget": _ADVICE_TOKEN_BUDGET,
        "lens": "postplan",
        "ids": [i["id"] for i in selected],
        "hints_used": hints,
    }
    return {"advice_items": selected, "advice_meta": meta}


# ─────────────────────────────────────────
# Budget-aware helpers (optional utilities)
# ─────────────────────────────────────────
def cap_list(items: list[Any], max_items: int) -> list[Any]:
    return items[:max_items] if max_items >= 0 else items


def cap_chars(text: str, max_chars: int) -> str:
    return text[:max_chars] if max_chars >= 0 else text


def estimate_tokens(text: str) -> int:
    # Rough estimator: ~4.3 chars/token
    return max(1, int(len(text) / 4.3))


__all__ = [
    # facets
    "lens_affective_facets",
    "lens_ethical_facets",
    "lens_safety_facets",
    "lens_mission_facets",
    "lens_style_facets",
    "lens_voice_facets",
    "lens_philosophical_facets",
    "lens_epistemic_facets",
    "lens_operational_facets",
    "lens_compliance_facets",
    "lens_simula_advice_preplan",
    "lens_simula_advice_postplan",
    # identity / state
    "lens_equor_identity",
    "lens_atune_salience",
    "lens_affect",
    "lens_event_canonical",
    "lens_retrieval_semantic",
    "lens_ecodia_self_concept",
    "lens_tools_catalog",
    "lens_get_tools",
    # utils
    "cap_list",
    "cap_chars",
    "estimate_tokens",
]
