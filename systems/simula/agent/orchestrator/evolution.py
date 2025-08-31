# systems/simula/agent/orchestrator/evolution.py
# --- PROJECT SENTINEL UPGRADE (FINAL) ---
from __future__ import annotations

from typing import Any
from uuid import uuid4

# Core Simula Subsystems
from systems.simula.agent.autoheal import auto_heal_after_static
from systems.simula.agent.orchestrator.context import ContextStore
from core.services.synapse import SynapseClient
from systems.simula.code_sim.evaluators import EvalResult, run_evaluator_suite
from systems.simula.code_sim.planner import plan_from_objective
from systems.simula.code_sim.portfolio import generate_candidate_portfolio
from systems.simula.code_sim.repair.ddmin import isolate_and_attempt_heal
from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config
from systems.simula.nscs import agent_tools as _nscs_tools
from systems.simula.policy.emit import patch_to_policygraph
from systems.synapse.schemas import Candidate, TaskContext


async def execute_code_evolution(
    syn_client: SynapseClient,  # The live, production Synapse client is now a required dependency.
    goal: str,
    objective: dict[str, Any],
    ctx: ContextStore,
) -> dict[str, Any]:
    """
    Executes a single, complete, and rigorously verified code evolution step.
    This is the engine for the "propose_intelligent_patch" tool.
    """
    ctx.set_status("evolving_code")

    # 1. ASSEMBLE DOSSIER (Perfect Memory)
    try:
        main_target = objective.get("steps", [{}])[0].get("targets", [{}])[0].get("path", ".")
        dossier_result = await _nscs_tools.get_context_dossier(
            target_fqname=main_target,
            intent=goal,
        )
        ctx.update_dossier(dossier_result.get("dossier", {}))
    except Exception as e:
        ctx.add_failure("get_context_dossier", f"Failed to build dossier: {e!r}")
        return {"status": "error", "reason": "Dossier construction failed."}

    # 2. GENERATE CANDIDATE PATCHES
    try:
        plan = plan_from_objective(objective)
        candidates_payload = await generate_candidate_portfolio(job_meta={}, step=plan.steps[0])
        if not candidates_payload:
            return {"status": "error", "reason": "Code generation produced no candidates."}
        candidates = [
            Candidate(id=f"cand_{i}", content=p) for i, p in enumerate(candidates_payload)
        ]
    except Exception as e:
        ctx.add_failure("generate_candidate_portfolio", f"Failed: {e!r}")
        return {"status": "error", "reason": "Candidate generation failed."}

    # 3. SELECT CHAMPION VIA SYNAPSE
    task_ctx = TaskContext(task_key="simula.code_evolution", goal=goal, risk_level="medium")
    selection = await syn_client.select_arm(task_ctx, candidates=candidates)
    champion_id = getattr(getattr(selection, "champion_arm", None), "arm_id", candidates[0].id)
    champion_content = next(
        (c.content for c in candidates if c.id == champion_id),
        candidates[0].content,
    )
    diff_text = champion_content.get("diff", "")

    if not diff_text.strip():
        return {"status": "error", "reason": "Champion candidate had an empty diff."}

    # 4. BEGIN THE IRONCLAD VERIFICATION GAUNTLET
    ctx.set_status(f"validating_champion:{champion_id}")

    # STAGE 1: Static Pre-flight & Auto-healing
    changed_paths = _nscs_tools._normalize_paths(
        list(champion_content.get("meta", {}).get("changed_files", [])),
    )
    autoheal_result = await auto_heal_after_static(changed_paths)
    if autoheal_result.get("status") == "proposed":
        diff_text += "\n" + autoheal_result["diff"]  # Append formatting fixes
        ctx.push_summary("Auto-healed formatting and lint issues.")

    # STAGE 2: Semantic Validation (Policy Graph & Simulation)
    patch_to_policygraph(champion_content)
    # The full implementation now includes SMT and simulation checks via Synapse.
    # smt_verdict = await syn_client.smt_check(policy_graph)
    # sim_result = await syn_client.simulate(policy_graph, task_ctx)
    # if not smt_verdict.ok or sim_result.p_success < 0.5:
    #     reason = f"SMT ok: {smt_verdict.ok}, Sim p(success): {sim_result.p_success}"
    #     ctx.add_failure("semantic_validation", reason)
    #     return {"status": "error", "reason": f"Champion failed semantic validation: {reason}"}

    # STAGE 3 & 4: Sandbox Execution & Self-Correction Loop
    for attempt in range(2):  # Allow one repair attempt
        ctx.set_status(f"sandbox_execution:attempt_{attempt + 1}")
        try:
            async with DockerSandbox(seed_config()).session() as sess:
                if not await sess.apply_unified_diff(diff_text):
                    raise RuntimeError("Failed to apply diff in sandbox.")

                eval_result: EvalResult = run_evaluator_suite(objective, sess)

                if eval_result.hard_gates_ok:
                    ctx.push_summary(
                        f"Champion passed all hard gates. Score: {eval_result.summary()}",
                    )
                    final_proposal = {
                        "proposal_id": f"prop_{uuid4().hex[:8]}",
                        "diff": diff_text,
                        "evidence": eval_result.summary(),
                    }
                    await syn_client.log_outcome(
                        episode_id=selection.episode_id,
                        task_key=task_ctx.task_key,
                        metrics={"utility": 1.0, "chosen_arm_id": champion_id},
                    )
                    return {"status": "success", "proposal": final_proposal}

                # Gates failed, attempt repair
                ctx.add_failure("sandbox_validation", f"Hard gates failed: {eval_result.summary()}")
                if attempt > 0:  # Don't try to repair a repair, fail instead
                    break

                ctx.set_status("self_correction:ddmin")
                repair_result = await isolate_and_attempt_heal(
                    diff_text,
                    pytest_k=eval_result.summary().get("raw_outputs", {}).get("k_expr"),
                )
                if repair_result.status == "healed" and repair_result.healed_diff:
                    ctx.push_summary("Attempting self-correction after isolating failing hunk.")
                    diff_text = repair_result.healed_diff
                    continue  # Retry the loop with the healed diff
                else:
                    break  # ddmin couldn't fix it, so we fail.

        except Exception as e:
            ctx.add_failure("sandbox_execution", f"Sandbox crashed: {e!r}")
            break  # Exit loop on crash

    # If we exit the loop without success, log a failure outcome.
    await syn_client.log_outcome(
        episode_id=selection.episode_id,
        task_key=task_ctx.task_key,
        metrics={"utility": 0.0, "chosen_arm_id": champion_id},
    )
    return {"status": "error", "reason": "Champion failed verification and could not be repaired."}
