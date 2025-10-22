# systems/synapse/core/planning_router.py
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter

from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.episode import start_episode
from systems.synapse.schemas import ArmScore, SelectArmRequest, SelectArmResponse
from systems.voxis.core.user_profile import build_context_for_voxis

planning_router = APIRouter(tags=["Synapse Planning"])
logger = logging.getLogger(__name__)

# --- Configuration ---
CONFIDENCE_THRESHOLD = 0.55
PLANNER_CACHE_TTL_SEC = 8.0

# Prevent invoking the LLM planner for simple “scorer/critic” tasks.
# ### FIX: include both dot/underscore spellings.
NO_PLANNER_TASK_KEYS = {
    "voxis_fact_critic",
    "voxis_utility_scorer",
    "equor_fact_critic",
    "equor_utility_scorer",
    "voxis_synthesis",
    "simula.utility_scorer",  # FIX
}

_PLANNER_CACHE: dict[str, tuple[float, SelectArmResponse]] = {}


# ------------------------
# Helpers (pure functions)
# ------------------------
def _mode_for_task_key(task_key: str) -> str:
    tk = (task_key or "").lower()
    if "critic" in tk or "scorer" in tk:
        return "generic"
    if "synthesis" in tk:
        return "synthesis"
    if tk.startswith("simula."):
        return "simula_planful"
    if tk.startswith("voxis."):
        return "voxis_planful"
    return "generic"


def _canonical_json(obj: Any) -> str:
    try:
        if hasattr(obj, "model_dump"):
            obj = obj.model_dump(mode="json")
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return json.dumps({"_repr": str(obj)})


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def extract_json_flex(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    m = re.search(r"(?:```json|```)\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start != -1:
        level = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                level += 1
            elif ch == "}":
                level -= 1
                if level == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


# ------------------------
# DB-first utilities
# ------------------------
async def _query_arms_for_mode(mode: str, limit: int = 5000) -> list[dict[str, Any]]:
    """
    Returns a list of dicts: {"id": <arm_id>, "metadata": {"mode": <mode>, "policy_graph": <parsed_or_raw>}}
    Filters out dynamic arms at the query level.
    """

    def process_rows(rows: list[dict]) -> list[dict[str, Any]]:
        processed = []
        for r in rows:
            if not r.get("id"):
                continue
            metadata = {
                "mode": r.get("mode"),
                "policy_graph": r.get("policy_graph"),
            }
            if isinstance(metadata["policy_graph"], str):
                try:
                    metadata["policy_graph"] = json.loads(metadata["policy_graph"])
                except json.JSONDecodeError:
                    pass
            processed.append({"id": r["id"], "metadata": metadata})
        return processed

    base_query = """
        MATCH (p:PolicyArm)
        WHERE {where_clause}
          AND coalesce(p.dynamic, false) = false
          AND NOT p.id STARTS WITH 'dyn::'
          AND NOT p.id STARTS WITH 'reflex::'
        RETURN p.id AS id, p.mode as mode, p.policy_graph as policy_graph
        ORDER BY p.id ASC
        LIMIT $limit
    """

    # strict match by mode first
    rows = (
        await cypher_query(
            base_query.format(where_clause="p.mode = $mode"),
            {"mode": mode, "limit": int(limit)},
        )
        or []
    )
    arms = process_rows(rows)
    if arms:
        return arms

    # family prefix fallbacks
    if mode == "simula_planful":
        where = "p.id STARTS WITH 'simula.planner.'"
        rows = (
            await cypher_query(base_query.format(where_clause=where), {"limit": int(limit)}) or []
        )
        return process_rows(rows)

    if mode == "voxis_planful":
        where = "p.id STARTS WITH 'voxis.planner.' OR p.id STARTS WITH 'voxis.agent.'"
        rows = (
            await cypher_query(base_query.format(where_clause=where), {"limit": int(limit)}) or []
        )
        return process_rows(rows)

    # generic catch-all
    rows = (
        await cypher_query(
            base_query.format(where_clause="coalesce(p.mode,'') <> ''"),
            {"limit": int(limit)},
        )
        or []
    )
    return process_rows(rows)


async def _ensure_safe_fallback() -> str:
    arm_id = "base.safe_fallback"  # or "generic.safe_fallback" if you prefer that name
    try:
        await cypher_query(
            """
            MERGE (p:PolicyArm {id: $id})
            ON CREATE SET
              p.mode       = 'generic',
              p.dynamic    = true,
              p.created_ts = timestamp()
            SET p.mode = coalesce(p.mode, 'generic')
            """,
            {"id": arm_id},
        )
    except Exception as e:
        logger.warning("Failed to ensure safe fallback arm '%s': %s", arm_id, e)
    return arm_id


def _pick_champion_arm(arms: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    """
    Select the best arm from the list for the mode.
    """
    if not arms:
        # ### FIX: default to base.safe_fallback
        return {"id": "base.safe_fallback", "metadata": {"mode": "generic"}}

    if mode == "simula_planful":
        for arm in arms:
            if arm.get("id", "").startswith("simula.planner."):
                return arm

    if mode == "voxis_planful":
        for arm in arms:
            if arm.get("id", "").startswith("voxis.planner."):
                return arm

    if mode == "generic":
        for arm in arms:
            if "scorer" in arm.get("id", ""):
                return arm
        for arm in arms:
            if "default" in arm.get("id", ""):
                return arm

    return arms[0]


async def _register_dynamic_arm(arm_id: str, policy_graph_meta: dict | None) -> None:
    try:
        await cypher_query(
            """
            MERGE (a:PolicyArm {id: $id})
            ON CREATE SET a.created_ts = timestamp()
            SET a.dynamic = true,
                a.mode = coalesce(a.mode, 'generic')
            """,
            {"id": arm_id},
        )
    except Exception as e:
        logger.warning("[DynamicArm] Graph registration failed for '%s': %s", arm_id, e)


async def _run_llm_planner(
    req: SelectArmRequest,
    episode_id: str,
    champion_arm: ArmScore,
    scope: str,
    summary: str,
    *,
    allow_dynamic: bool = True,
) -> SelectArmResponse:
    logger.info(
        "Episode %s: Invoking guided LLM planner (scope: %s) with base arm '%s'.",
        episode_id,
        scope,
        champion_arm.arm_id,
    )

    context_dict = req.task_ctx.model_dump()
    context_dict.update(
        {
            "episode_id": episode_id,
            "selected_policy_hints": champion_arm.policy_graph_meta or {},
            "selected_arm_id": champion_arm.arm_id,
            "strategy_arm": champion_arm.arm_id,
        },
    )

    if scope.startswith("voxis"):
        context_dict["memory"] = await build_context_for_voxis(
            user_id=(req.task_ctx.metadata or {}).get("user_id"),
            session_id=(req.task_ctx.metadata or {}).get("session_id"),
            user_input=req.task_ctx.goal,
        )

    try:
        prompt_response = await build_prompt(scope=scope, context=context_dict, summary=summary)
        llm_response = await call_llm_service(
            prompt_response,
            agent_name="Synapse.Planner",
            scope=scope,
            arm_id=champion_arm.arm_id,
        )
        plan_obj = extract_json_flex(getattr(llm_response, "text", "")) or {
            "plan": [],
            "thought": "Planner failed to generate a valid plan.",
        }

        if allow_dynamic:
            content_hash = _sha256(_canonical_json(plan_obj))
            dynamic_arm_id = f"dyn::{content_hash[:16]}"
            await _register_dynamic_arm(dynamic_arm_id, champion_arm.policy_graph_meta or {})
            await cypher_query(
                "MATCH (e:Episode {id: $id}) SET e.chosen_arm_id = $arm_id",
                {"id": episode_id, "arm_id": dynamic_arm_id},
            )
            return SelectArmResponse(
                episode_id=episode_id,
                champion_arm=ArmScore(
                    arm_id=dynamic_arm_id,
                    score=1.0,
                    reason=f"LLM-generated plan based on initial selection '{champion_arm.arm_id}'.",
                    content=plan_obj,
                    policy_graph_meta=champion_arm.policy_graph_meta,
                ),
                shadow_arms=[],
            )
        else:
            await cypher_query(
                "MATCH (e:Episode {id: $id}) SET e.chosen_arm_id = $arm_id",
                {"id": episode_id, "arm_id": champion_arm.arm_id},
            )
            return SelectArmResponse(
                episode_id=episode_id,
                champion_arm=ArmScore(
                    arm_id=champion_arm.arm_id,
                    score=max(1.0, champion_arm.score or 0.0),
                    reason="Planner content attached without creating a dynamic arm.",
                    content=plan_obj,
                    policy_graph_meta=champion_arm.policy_graph_meta,
                ),
                shadow_arms=[],
            )
    except Exception as e:
        logger.error(
            "Episode %s: LLM Planner failed (base arm: %s): %s",
            episode_id,
            champion_arm.arm_id,
            e,
            exc_info=True,
        )
        fb_id = await _ensure_safe_fallback()
        return SelectArmResponse(
            episode_id=episode_id,
            champion_arm=ArmScore(
                arm_id=fb_id,
                score=0.0,
                reason=f"Planner failure fallback: {e}",
                content={"plan": [], "thought": f"Critical planner failure: {e}"},
            ),
            shadow_arms=[],
        )


def _planner_cache_key(mode: str, req: SelectArmRequest, champion_arm_id: str) -> str:
    meta = req.task_ctx.metadata or {}
    basis = {
        "mode": mode,
        "task_key": req.task_ctx.task_key,
        "goal": req.task_ctx.goal,
        "turn": meta.get("turn"),
        "base_arm": champion_arm_id,
    }
    return _sha256(_canonical_json(basis))


def _planner_cache_get(key: str) -> SelectArmResponse | None:
    now = time.monotonic()
    item = _PLANNER_CACHE.get(key)
    if not item:
        return None
    ts, resp = item
    if (now - ts) > PLANNER_CACHE_TTL_SEC:
        _PLANNER_CACHE.pop(key, None)
        return None
    return resp


def _planner_cache_put(key: str, resp: SelectArmResponse) -> None:
    _PLANNER_CACHE[key] = (time.monotonic(), resp)


@planning_router.post("/select_or_plan", response_model=SelectArmResponse)
async def select_or_plan(req: SelectArmRequest) -> SelectArmResponse:
    task_key = req.task_ctx.task_key
    mode = _mode_for_task_key(task_key)

    meta = req.task_ctx.metadata or {}
    exclude_prefixes = tuple(meta.get("arm_id_exclude_prefixes", []))
    static_only = any(pfx.startswith("dyn::") for pfx in exclude_prefixes) or any(
        pfx.startswith("reflex::") for pfx in exclude_prefixes
    )

    try:
        arms_with_meta = await _query_arms_for_mode(mode)
    except Exception as e:
        logger.error("DB query for mode '%s' failed: %s", mode, e, exc_info=True)
        arms_with_meta = []

    if arms_with_meta and exclude_prefixes:
        arms_with_meta = [
            a
            for a in arms_with_meta
            if not any(str(a.get("id", "")).startswith(p) for p in exclude_prefixes)
        ]

    if not arms_with_meta:
        chosen_id = await _ensure_safe_fallback()  # ### FIX: yields base.safe_fallback
        chosen_metadata = {"mode": "generic"}
        top_score = 0.0
    else:
        chosen_arm_dict = _pick_champion_arm(arms_with_meta, mode)
        chosen_id = chosen_arm_dict.get("id", "base.safe_fallback")  # ### FIX default
        chosen_metadata = chosen_arm_dict.get("metadata", {})
        top_score = 1.0

    episode_id = await start_episode(
        mode=mode,
        task_key=task_key,
        chosen_arm_id=chosen_id,
        context=req.task_ctx.model_dump(),
    )

    initial_champion_score = ArmScore(
        arm_id=chosen_id,
        score=top_score,
        reason="DB-first selection.",
        policy_graph_meta=chosen_metadata,
        content=None,
    )
    shadow_arms = [
        ArmScore(
            arm_id=arm["id"],
            score=0.5,
            reason="DB candidate.",
            policy_graph_meta=arm.get("metadata", {}),
        )
        for arm in arms_with_meta
        if arm.get("id") != chosen_id
    ][:5]

    if task_key in NO_PLANNER_TASK_KEYS:
        return SelectArmResponse(
            episode_id=episode_id,
            champion_arm=initial_champion_score,
            shadow_arms=shadow_arms,
        )

    if mode == "voxis_planful" and top_score < CONFIDENCE_THRESHOLD and not static_only:
        scope = "voxis.main.planning"
        summary = "Voxis agentic planning for a conversational turn."
        cache_key = _planner_cache_key(mode, req, chosen_id)
        if cached := _planner_cache_get(cache_key):
            cached.episode_id = episode_id
            return cached
        resp = await _run_llm_planner(
            req,
            episode_id,
            initial_champion_score,
            scope,
            summary,
            allow_dynamic=True,
        )
        _planner_cache_put(cache_key, resp)
        return resp

    if mode == "generic" and top_score < CONFIDENCE_THRESHOLD and not static_only:
        scope = "synapse.generic.planning"
        summary = "Generic Synapse planning for a low-confidence task."
        cache_key = _planner_cache_key(mode, req, chosen_id)
        if cached := _planner_cache_get(cache_key):
            cached.episode_id = episode_id
            return cached
        resp = await _run_llm_planner(
            req,
            episode_id,
            initial_champion_score,
            scope,
            summary,
            allow_dynamic=True,
        )
        _planner_cache_put(cache_key, resp)
        return resp

    return SelectArmResponse(
        episode_id=episode_id,
        champion_arm=initial_champion_score,
        shadow_arms=shadow_arms,
    )
