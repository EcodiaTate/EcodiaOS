# systems/simula/nscs/evolution.py
from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

# Core EcodiaOS Services & Schemas
from core.services.synapse import SynapseClient
from systems.qora import api_client as qora_client

# Simula Core Subsystems
from systems.simula.agent.autoheal import auto_heal_after_static
from systems.simula.code_sim.evaluators import EvalResult, run_evaluator_suite
from systems.simula.code_sim.portfolio import generate_candidate_portfolio
from systems.simula.code_sim.repair.ddmin import isolate_and_attempt_heal
from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config
from systems.simula.policy.emit import patch_to_policygraph
from systems.synapse.schemas import Candidate, PatchProposal, TaskContext

from .context import ContextStore

logger = logging.getLogger(__name__)

# --- Helper Functions (ported from old orchestrator) ---


def _is_self_upgrade(changed_paths: list[str]) -> bool:
    """Determines if a patch modifies Simula's own source code."""
    return any(p.startswith("systems/simula/") for p in changed_paths)


_DIFF_FILE_RE = re.compile(r"^[+-]{3}\s+(?P<label>.+)$")
_STRIP_PREFIX_RE = re.compile(r"^(a/|b/)+")


def _extract_paths_from_unified_diff(diff_text: str) -> list[str]:
    """Extract unique repo-relative paths from a unified diff string."""
    if not isinstance(diff_text, str) or not diff_text:
        return []
    paths: list[str] = []
    seen = set()
    for line in diff_text.splitlines():
        m = _DIFF_FILE_RE.match(line)
        if not m:
            continue
        label = m.group("label").strip()
        if label == "/dev/null":
            continue
        p = _STRIP_PREFIX_RE.sub("", label)
        if not p or p == ".":
            continue
        if p not in seen:
            seen.add(p)
            paths.append(p)
    return paths


# --- Main Evolution Engine ---


async def execute_code_evolution(*, goal: str, objective: dict) -> dict[str, Any]:
    """
    Executes a single, complete, and rigorously verified code evolution step.
    This is the self-contained engine for the "propose_intelligent_patch" tool.
    """
    logger.info("Starting code evolution cycle for goal: %s", goal)

    evo_id = f"evo_{uuid4().hex[:8]}"
    ctx = ContextStore(run_dir=f"artifacts/runs/{evo_id}")
    syn_client = SynapseClient()

    ctx.set_status("evolving_code")

    # === STAGE 1: ASSEMBLE DOSSIER ===
    ctx.set_status("assembling_dossier")
    try:
        main_target = objective.get("target_fqname", ".")
        dossier_result = await qora_client.get_dossier(
            target_fqname=main_target, intent="implement"
        )
        ctx.update_dossier(dossier_result)
        logger.info("Successfully assembled dossier for target: %s", main_target)
    except Exception as e:
        return {"status": "error", "reason": f"Dossier construction failed: {e!r}"}

    # === STAGE 2: GENERATE CANDIDATE PORTFOLIO ===
    ctx.set_status("generating_candidates")
    try:
        # FIXED: The keyword argument was incorrect. According to the refactoring note,
        # the function now expects 'objective' instead of the legacy 'step_dict'.
        # This aligns the call with the intended modern architecture.
        candidates_payload = await generate_candidate_portfolio(job_meta={}, objective=objective)

        if not candidates_payload:
            return {"status": "error", "reason": "Code generation produced no candidates."}
        candidates = [
            Candidate(id=f"cand_{i}", content=p) for i, p in enumerate(candidates_payload)
        ]
    except Exception as e:
        logger.error(f"Candidate generation failed: {e!r}", exc_info=True)
        return {"status": "error", "reason": f"Candidate generation failed: {e!r}"}

    # === STAGE 3: SELECT CHAMPION VIA SYNAPSE ===
    ctx.set_status("selecting_champion")
    task_ctx = TaskContext(task_key="simula.code_evolution.select", goal=goal, risk_level="high")
    selection = await syn_client.select_arm(task_ctx, candidates=candidates)
    champion_content = next(
        (c.content for c in candidates if c.id == selection.champion_arm.arm_id),
        candidates[0].content,
    )
    diff_text = champion_content.get("diff", "")
    if not diff_text.strip():
        return {"status": "error", "reason": "Champion candidate had an empty diff."}

    # === STAGE 4: VERIFICATION GAUNTLET ===
    ctx.set_status(f"validating_champion:{selection.champion_arm.arm_id}")
    changed_paths = _extract_paths_from_unified_diff(diff_text)

    # Auto-healing
    autoheal_result = await auto_heal_after_static(changed_paths)
    if autoheal_result.get("status") == "proposed":
        diff_text += "\n" + autoheal_result.get("diff", "")
        ctx.push_summary("Auto-healed formatting and lint issues.")

    # Self-Upgrade Governance Escalation
    if _is_self_upgrade(changed_paths):
        proposal = PatchProposal(summary=f"Simula self-upgrade: {goal}", diff=diff_text)
        return await syn_client.submit_upgrade_proposal(proposal)

    # Sandbox Execution & Self-Correction Loop
    for attempt in range(2):  # Allow one repair attempt
        ctx.set_status(f"sandbox_execution:attempt_{attempt + 1}")
        try:
            async with DockerSandbox(seed_config()).session() as sess:
                if not await sess.apply_unified_diff(diff_text):
                    raise RuntimeError("Failed to apply diff in sandbox.")

                eval_result: EvalResult = await run_evaluator_suite(objective, sess)

                if eval_result.hard_gates_ok:
                    final_proposal = {
                        "proposal_id": f"prop_{evo_id}",
                        "diff": diff_text,
                        "evidence": eval_result.summary(),
                    }
                    await syn_client.log_outcome(
                        episode_id=selection.episode_id,
                        task_key=task_ctx.task_key,
                        arm_id=selection.champion_arm.arm_id,
                        metrics={"utility": 1.0, **eval_result.summary()},
                    )
                    return {"status": "success", "proposal": final_proposal}

                # Gates failed, attempt repair
                failure_summary = (
                    f"Hard gates failed on attempt {attempt + 1}: {eval_result.summary()}"
                )
                ctx.add_failure("sandbox_validation", failure_summary)
                if attempt > 0:
                    break

                ctx.set_status("self_correction:ddmin")
                repair_result = await isolate_and_attempt_heal(diff_text)
                if repair_result.status == "healed" and repair_result.healed_diff:
                    diff_text = repair_result.healed_diff
                    continue  # Retry the loop with the healed diff
                else:
                    break  # ddmin couldn't fix it

        except Exception as e:
            ctx.add_failure("sandbox_execution", f"Sandbox crashed: {e!r}")
            break

    # If loop finishes without success
    await syn_client.log_outcome(
        episode_id=selection.episode_id,
        task_key=task_ctx.task_key,
        arm_id=selection.champion_arm.arm_id,
        metrics={"utility": 0.0, "reason": "verification_failed"},
    )
    return {"status": "error", "reason": "Champion failed verification and could not be repaired."}
