# api/endpoints/synapse/tasks.py
# FIXED VERSION (JSON-safe Episode persistence)
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.firewall import neuro_symbolic_firewall
from systems.synapse.core.registry import arm_registry
from systems.synapse.core.tactics import tactical_manager
from systems.synapse.critic.offpolicy import critic
from systems.synapse.schemas import (
    ArmScore,
    SelectArmRequest,
    SelectArmResponse,
)
from systems.synapse.skills.manager import skills_manager
from systems.synapse.training.neural_linear import neural_linear_manager
from systems.synapse.world.simulator import world_model

task_router = APIRouter(tags=["Synapse Tasks"])


def _j(x: Any) -> str:
    return json.dumps(x, separators=(",", ":"), ensure_ascii=False)


async def _persist_episode_json_safe(
    *,
    mode: str,
    task_key: str,
    chosen_arm_id: str,
    context_dict: dict[str, Any],
    audit_trace_dict: dict[str, Any],
) -> str:
    episode_id = f"ep::{uuid.uuid4()}"
    try:
        await cypher_query(
            """
            MERGE (e:Episode {id:$id})
            SET e.task_key       = $task_key,
                e.cognitive_mode = $mode,
                e.chosen_arm_id  = $chosen_arm_id,
                e.context        = $context_json,
                e.audit_trace    = $audit_json,
                e.created_at     = datetime()
            """,
            {
                "id": episode_id,
                "task_key": task_key,
                "mode": mode,
                "chosen_arm_id": chosen_arm_id,
                "context_json": _j(context_dict),
                "audit_json": _j(audit_trace_dict),
            },
        )
    except Exception as e:
        print(f"[EpisodePersist] Non-fatal write failure: {e}")
    return episode_id


def _is_no_arms_err(e: Exception) -> bool:
    m = str(e).lower()
    return "no arms found" in m or "no arms" in m


@task_router.post("/select_arm", response_model=SelectArmResponse)
async def select_arm(req: SelectArmRequest):
    print(f"[API] /synapse/select_arm called for task: {req.task_ctx.task_key}")

    # 1) encode context
    try:
        x_context = neural_linear_manager.encode(req.task_ctx.model_dump())
    except Exception as e:
        print(f"[API] encode failed, using zero vector: {e}")
        x_context = []

    # 2) hierarchical option (best-effort)
    try:
        matched = skills_manager.select_best_option(x_context, req.task_ctx)
        if matched:
            first_arm = arm_registry.get_arm(matched.policy_sequence[0])
            if first_arm:
                ep_id = await _persist_episode_json_safe(
                    mode="option_execution",
                    task_key=req.task_ctx.task_key,
                    chosen_arm_id=first_arm.id,
                    context_dict=req.task_ctx.model_dump(),
                    audit_trace_dict={"activated_option_id": matched.id},
                )
                return SelectArmResponse(
                    episode_id=ep_id,
                    champion_arm=ArmScore(
                        arm_id=first_arm.id,
                        score=matched.expected_reward,
                        reason=f"Hierarchical Skill: Step 1/{len(matched.policy_sequence)}",
                    ),
                    shadow_arms=[],
                )
    except Exception as e:
        print(f"[API] option select failed (continuing): {e}")

    # 3) OOD → risk bump (optional)
    try:
        # if you have an OOD detector wired, call it here
        pass
    except Exception:
        pass

    # 4/5) tactics + fallback
    try:
        mode = "planful"
        _, cand_scores = tactical_manager.select_arm(req, mode)
    except Exception as e:
        if _is_no_arms_err(e):
            safe = arm_registry.get_safe_fallback_arm("planful")
            cand_scores = {safe.id: 0.0}
            mode = "planful"
        else:
            print(f"[API] tactics failed: {e}; using safe fallback")
            safe = arm_registry.get_safe_fallback_arm("planful")
            cand_scores = {safe.id: 0.0}
            mode = "planful"

    # 6) critic re-rank (best-effort)
    try:
        champion_id = await critic.rerank_topk(req.task_ctx, cand_scores, blend_factor=0.0)
    except Exception as e:
        print(f"[API] critic rerank failed: {e}")
        champion_id = max(cand_scores, key=cand_scores.get)

    # 7) world-model adjustment (best-effort)
    try:
        final_scores: dict[str, float] = {}
        for aid, s in cand_scores.items():
            arm = arm_registry.get_arm(aid)
            if not arm:
                continue
            pred = await world_model.simulate(arm.policy_graph, req.task_ctx)
            final_scores[aid] = s - 0.2 * getattr(pred, "delta_cost", 0.0)
    except Exception as e:
        print(f"[API] world model adjust failed: {e}")
        final_scores = cand_scores

    champ_id = max(final_scores, key=final_scores.get) if final_scores else champion_id
    champ_arm = arm_registry.get_arm(champ_id) or arm_registry.get_safe_fallback_arm("planful")

    # 8) firewall (best-effort)
    try:
        is_safe, reason = await neuro_symbolic_firewall.validate_action(champ_arm, req.task_ctx)
    except Exception as e:
        print(f"[API] firewall validate failed: {e}")
        is_safe, reason = True, "firewall_unavailable"
    if not is_safe:
        orig = champ_arm.id
        champ_arm = neuro_symbolic_firewall.get_safe_fallback_arm("planful")
        print(f"[API] Firewall swap {orig} -> {champ_arm.id} ({reason})")

    # 9) small explanation (best-effort)
    try:
        shadow_ids = [aid for aid in cand_scores if aid != champ_arm.id]
        explanation = {"minset": ["N/A"], "flip_to_arm": shadow_ids[0] if shadow_ids else "N/A"}
    except Exception:
        shadow_ids = [aid for aid in cand_scores if aid != champ_arm.id]
        explanation = {"minset": ["N/A"], "flip_to_arm": "N/A"}

    # 10) audit + episode (JSON-safe)
    audit = {
        "bandit_scores": cand_scores,
        "final_scores": final_scores,
        "explanation": explanation,
        "firewall": {"is_safe": is_safe, "reason": reason},
    }
    episode_id = await _persist_episode_json_safe(
        mode="planful",
        task_key=req.task_ctx.task_key,
        chosen_arm_id=champ_arm.id,
        context_dict=req.task_ctx.model_dump(),
        audit_trace_dict=audit,
    )

    # 11) respond
    return SelectArmResponse(
        episode_id=episode_id,
        champion_arm=ArmScore(
            arm_id=champ_arm.id,
            score=final_scores.get(champ_arm.id, 0.0),
            reason="Final Selection",
        ),
        shadow_arms=[
            ArmScore(arm_id=aid, score=s, reason="Candidate")
            for aid, s in final_scores.items()
            if aid != champ_arm.id
        ][:5],
    )
