# api/endpoints/synapse/main.py
# FINAL PRODUCTION VERSION (hardened, deduped)
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

# --- Synapse Core Cognitive & Skill Modules ---
from systems.synapse.core.meta_controller import meta_controller
from systems.synapse.core.registry import arm_registry
from systems.synapse.core.tactics import tactical_manager

# --- Schema Imports ---
from systems.synapse.schemas import (
    ArmScore,
    BudgetResponse,
    ContinueRequest,
    ContinueResponse,
    HintRequest,
    HintResponse,
    RepairRequest,
    RepairResponse,
    SelectArmRequest,
    TaskContext,
)
from systems.synapse.skills.executor import option_executor

# --- The single, unified router for all Synapse endpoints ---
main_router = APIRouter()
logger = logging.getLogger(__name__)

# =======================================================================
# == Core Task Execution Endpoints
# =======================================================================


@main_router.post("/tasks/continue_option", response_model=ContinueResponse)
async def continue_option(req: ContinueRequest):
    """Continues the execution of a multi-step skill (Option)."""
    logger.info("[API] /tasks/continue_option episode=%s", req.episode_id)

    next_arm = option_executor.continue_execution(req.episode_id, req.last_step_outcome)

    if not next_arm:
        return ContinueResponse(episode_id=req.episode_id, next_action=None, is_complete=True)

    # Correctly construct the ArmScore object for the 'next_action' field.
    next_action_score = ArmScore(
        arm_id=next_arm.id,
        score=1.0,
        reason="Hierarchical Skill: Next Step",
    )

    return ContinueResponse(
        episode_id=req.episode_id,
        next_action=next_action_score,
        is_complete=False,
    )


@main_router.post("/tasks/repair_skill_step", response_model=RepairResponse)
async def repair_skill_step(req: RepairRequest):
    """Generates a targeted, one-shot repair action for a failed step in a skill."""
    logger.info(
        "[API] /tasks/repair_skill_step episode=%s failed_step=%s",
        req.episode_id,
        req.failed_step_index,
    )

    # Force a planful cognitive mode for careful repair
    repair_task_ctx = TaskContext(
        task_key="synapse_skill_repair",
        goal=f"Repair failed step {req.failed_step_index}. Error: {req.error_observation.get('status')}",
        risk_level="high",
        budget="normal",
    )

    # Let TacticalManager generate candidates (empty candidates list)
    try:
        repair_arm, _ = tactical_manager.select_arm(
            SelectArmRequest(task_ctx=repair_task_ctx, candidates=[]),
            "generic",
        )
        arm_id = repair_arm.id
    except Exception as e:
        logger.warning("[API] repair tactics failed, using safe fallback: %s", e)
        arm_id = await arm_registry.get_safe_fallback_arm("generic").id

    return RepairResponse(
        episode_id=req.episode_id,
        repair_action=ArmScore(arm_id=arm_id, score=1.0, reason="Targeted Repair Action"),
        notes=f"Synapse suggests using '{arm_id}' to repair the failed step.",
    )


@main_router.get("/tasks/{task_key}/budget", response_model=BudgetResponse)
async def get_budget(task_key: str):
    """Returns a resource budget for a task."""
    logger.info("[API] /tasks/%s/budget", task_key)
    try:
        strat_budget: dict[str, Any] = meta_controller.allocate_budget(
            TaskContext(task_key=task_key, risk_level="medium"),
        )
        tokens = int(strat_budget.get("tokens", 8192))
        cost_units = int(strat_budget.get("cost_units", 3))

        # Convert MetaController budget into API limits
        wall_ms = int(60_000 * max(1, min(10, cost_units)) * 5)  # 5 min per unit (cap 10)
        cpu_ms = int(30_000 * max(1, min(10, cost_units)) * 4)  # 2 min per unit *2

        return BudgetResponse(tokens_max=tokens, wall_ms_max=wall_ms, cpu_ms_max=cpu_ms)
    except Exception as e:
        logger.warning("[API] budget fallback: %s", e)
        # Safe defaults
        return BudgetResponse(tokens_max=8192, wall_ms_max=300_000, cpu_ms_max=120_000)


async def get_real_hint(namespace: str, key: str, context: dict) -> Any:
    """
    Derives a hint by selecting the best policy arm for the current context
    and extracting the desired parameter from its policy graph.
    """
    try:
        # 1. Create a TaskContext from the hint's context to find the best arm.
        risk_level = context.get("risk_level", "medium")
        if risk_level == "normal":
            risk_level = "medium"

        task_ctx = TaskContext(
            task_key=f"hint.{namespace}.{key}",
            goal=f"Find best '{key}' for {namespace}",
            risk_level=risk_level,
            budget=context.get("budget", "normal"),
        )

        # 2. Use the core Tactical Manager to select the champion arm.
        # We pass an empty candidate list to let the manager consider all applicable arms.
        select_req = SelectArmRequest(task_ctx=task_ctx, candidates=[])
        champion_arm, _ = await tactical_manager.select_arm(select_req, "generic")

        if not champion_arm:
            return None

        # 3. Get the full arm policy from the registry.
        full_arm = arm_registry.get_arm(champion_arm.id)
        if not full_arm or not full_arm.policy_graph:
            return None

        # 4. Extract the hint from the policy graph's parameters.
        # This assumes hints are stored in a 'params' dictionary within the policy graph.
        policy_graph_data = None
        if hasattr(full_arm, "policy_graph_json"):
            policy_graph_data = full_arm.policy_graph_json
        elif hasattr(full_arm, "policy_graph"):
            policy_graph_data = full_arm.policy_graph

        if not policy_graph_data:
            return None

        # Safely parse the data, whether it's a string or already a dict
        policy_graph_dict = {}
        if isinstance(policy_graph_data, str):
            policy_graph_dict = json.loads(policy_graph_data)
        elif isinstance(policy_graph_data, dict):
            policy_graph_dict = policy_graph_data

        policy_params = policy_graph_dict.get("params", {})
        return policy_params.get(key)

    except Exception as e:
        logger.warning(f"[Hints] Could not derive real hint for '{namespace}.{key}': {e}")
        return None


@main_router.post("/hint", response_model=HintResponse, tags=["Synapse Tasks"])
async def get_hint(req: HintRequest):
    """
    Provides dynamic, context-aware configuration hints to other services
    by leveraging the currently optimal policy arm.
    """
    logger.info("[API] /synapse/hint called for namespace=%s, key=%s", req.namespace, req.key)

    value = await get_real_hint(req.namespace, req.key, req.context)

    return HintResponse(
        value=value,
        meta={
            "source": "synapse-tactics-derived",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


# =======================================================================
# == System & Registry Management
# =======================================================================


@main_router.get("/", tags=["Root"])
async def read_root():
    return {"status": "Synapse Cognitive Engine is online and operational."}
