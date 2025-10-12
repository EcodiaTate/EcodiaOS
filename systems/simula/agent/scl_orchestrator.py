# systems/simula/agent/scl_orchestrator.py
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.llm.embeddings_gemini import get_embedding as embed_text

# --- Core Cognitive Components ---
from core.prompting.orchestrator import build_prompt
from core.services.qora import QoraClient
from core.services.synapse import SynapseClient
from core.utils.llm_gateway_client import call_llm_service, extract_json_flex
from systems.simula.code_sim.telemetry import get_tracked_tools
from systems.simula.memory.schemas import SynapticTrace
from systems.simula.memory.trace_db import TraceDBClient
from systems.synapse.schemas import ArmScore, SelectArmResponse, TaskContext

# --- Agent Sub-systems ---
from .deliberation import DeliberationRoom
from .dispatcher import dispatch_tool
from .runlog import RunLogger
from .scl_context import Blackboard, WorkingContext, synthesize_context
from .scl_utils import _inject_target_defaults, _run_utility_scorer

log = logging.getLogger(__name__)


def _resolve_sandbox_paths(params: dict[str, Any]) -> dict[str, Any]:
    sandbox_root = os.getenv("SANDBOX_ROOT", "/app")
    if not isinstance(params, dict):
        return params

    def _fix(v: Any) -> Any:
        if isinstance(v, str):
            if v.startswith(sandbox_root) or v.startswith("/") or "://" in v:
                return v
            if ("/" in v) or v.endswith((".py", ".txt", ".md")):
                return os.path.join(sandbox_root, v.lstrip("/"))
            return v
        if isinstance(v, list):
            return [_fix(x) for x in v]
        if isinstance(v, dict):
            return {k: _fix(x) for k, x in v.items()}
        return v

    return {k: _fix(v) for k, v in params.items()}


class SCL_Orchestrator:
    """
    Manages the full cognitive cycle for the MDO, prioritizing reflexes (System 1)
    over deliberation (System 2).
    """

    def __init__(self, session_id: str, synapse_client: SynapseClient | None = None):
        self.session_id = session_id or uuid4().hex
        self.synapse = synapse_client or SynapseClient()
        self.blackboard = Blackboard(session_id=self.session_id)
        self.deliberation_room = DeliberationRoom()

        # --- Cognitive Function Clients ---
        self.trace_db = TraceDBClient()
        self.qora = QoraClient()

        self.full_tool_map = get_tracked_tools()
        log.info(f"[SCL] Initialized with {len(self.full_tool_map)} tools in the global registry.")

    def _apply_context_lens(self, mode: str) -> list[dict[str, Any]]:
        """
        Filters the global tool map to return only tools relevant for the given mode.
        """
        if not mode:
            mode = "general"

        lensed_tools = []
        for tool_name, meta in self.full_tool_map.items():
            tool_modes = meta.get("modes", ["general"])
            if mode in tool_modes or "general" in tool_modes:
                func = meta.get("func")
                if not func:
                    continue

                try:
                    sig = inspect.signature(func)
                    params_str = ", ".join(str(p) for p in sig.parameters.values())
                    signature_str = f"{tool_name}({params_str})"

                    lensed_tools.append(
                        {
                            "name": tool_name,
                            "signature": signature_str,
                            "description": inspect.getdoc(func) or "No description available.",
                        }
                    )
                except Exception:
                    lensed_tools.append(
                        {
                            "name": tool_name,
                            "signature": f"{tool_name}(...)",
                            "description": inspect.getdoc(func) or "No description available.",
                        }
                    )

        log.info(
            f"[SCL] Applied context lens for mode '{mode}', providing {len(lensed_tools)} tools."
        )
        return lensed_tools

    async def _generate_triggering_state_vector(
        self,
        goal: str,
        target_fqname: str | None,
        error_context: str | None = None,
    ) -> list[float]:
        """
        Creates a rich "problem fingerprint" embedding to represent the current task.
        """
        text_blob = f"GOAL: {goal}\n\nERROR: {error_context or 'None'}"

        if target_fqname:
            try:
                dossier = await asyncio.wait_for(self.qora.get_dossier(target_fqname), timeout=15.0)
                target_code = dossier.get("target", {}).get("source_code", "")
                summary = dossier.get("summary", "")
                text_blob += f"\n\nTARGET CONTEXT: {summary}\n\nCODE:\n{target_code}"
            except TimeoutError:
                log.warning(
                    f"[SCL] Dossier generation for '{target_fqname}' timed out during state vector creation."
                )
                text_blob += f"\n\nTARGET: {target_fqname}"
            except Exception as e:
                log.error(f"[SCL] Dossier generation failed during state vector creation: {e!r}")
                text_blob += f"\n\nTARGET: {target_fqname}"

        return await embed_text(text_blob, task_type="RETRIEVAL_QUERY")

    async def run(
        self,
        *,
        goal: str,
        dossier: dict,
        target_fqname: str | None,
        error_context: str | None = None,
    ) -> dict[str, Any]:
        """Executes a full, single-turn invocation of the agent's cognitive cycle."""
        runlog = RunLogger(session_id=self.session_id, goal=goal, target_fqname=target_fqname)
        await self.blackboard.load_from_memory()
        log.info(
            "[SCL] Loaded %d turns for session '%s'.",
            len(self.blackboard.turn_history),
            self.session_id,
        )

        execution_results: dict[str, Any] = {}
        final_plan: dict[str, Any] | list[dict[str, Any]] = {}
        plan_steps: list[dict[str, Any]] = []
        episode_id: str | None = None
        was_reflex = False
        state_vector: list[float] = []

        # --- PHASE 1: REFLEX ARC (SYSTEM 1) ---
        try:
            state_vector = await self._generate_triggering_state_vector(
                goal, target_fqname, error_context
            )
            matching_trace = await self.trace_db.search(
                state_vector, min_confidence=0.8, similarity_threshold=0.98
            )
        except Exception as e:
            log.error(f"[SCL-S1] Reflex Arc failed during search: {e!r}", exc_info=True)
            matching_trace = None

        if matching_trace:
            was_reflex = True
            log.info(
                f"[SCL-S1] ⚡️ Reflex Arc Fired! Executing known successful trace: {matching_trace.trace_id}"
            )
            runlog.log_note(
                "reflex_arc_fired",
                {
                    "trace_id": matching_trace.trace_id,
                    "confidence": matching_trace.confidence_score,
                },
            )

            plan_steps = matching_trace.action_sequence
            final_plan = {
                "plan": plan_steps,
                "dynamic_plan_arm_id": f"reflex::{matching_trace.trace_id}",
            }

            log.info("[SCL] Phase 3: Executing %d reflexive steps.", len(plan_steps))
            execution_results = await self._execute_plan(plan_steps, runlog=runlog, goal=goal)
            episode_id = f"reflex_ep_{uuid4().hex}"

        else:
            log.info("[SCL-S2] 🧠 No reflex found. Engaging Deliberative Core.")

            # --- PHASE 2: DELIBERATIVE CORE (SYSTEM 2) ---
            task_ctx = TaskContext(
                task_key="simula.agent.turn",
                goal=goal,
                metadata={"target_fqname": target_fqname, "dossier_provided": bool(dossier)},
            )
            try:
                selection = await self.synapse.select_or_plan(task_ctx, candidates=[])
                episode_id = selection.episode_id

                _pgm = selection.champion_arm.policy_graph_meta or {}
                champion_arm_mode = _pgm.get("mode", "simula_planful")
                lensed_tools = self._apply_context_lens(champion_arm_mode)

                working_context = await synthesize_context(
                    strategy_arm=selection.champion_arm,
                    goal=goal,
                    target_fqname=target_fqname,
                    dossier=dossier,
                    blackboard=self.blackboard,
                    lensed_tools=lensed_tools,
                )

                deliberation_result = await self.deliberation_room.deliberate(
                    working_context=working_context,
                    mode=champion_arm_mode,
                    runlog=runlog,
                )

            except Exception as e:
                msg = f"Deliberative Core failed during planning: {e!r}"
                log.error("[SCL-S2] CRITICAL: %s", msg, exc_info=True)
                runlog.log_outcome(
                    status="error", episode_id=episode_id, utility_score=None, notes={"reason": msg}
                )
                runlog.save()
                return {"status": "error", "reason": msg}

            if deliberation_result.status != "approved":
                msg = f"Plan rejected: {deliberation_result.reason}"
                log.warning(f"[SCL-S2] {msg}")
                runlog.log_outcome(
                    status="error",
                    episode_id=episode_id,
                    utility_score=None,
                    notes={"deliberation": deliberation_result.model_dump()},
                )
                runlog.save()
                return {
                    "status": "error",
                    "reason": msg,
                    "deliberation": deliberation_result.model_dump(),
                }

            # --- PHASE 3: EXECUTION ---
            final_plan = deliberation_result.final_plan
            plan_steps = final_plan.get("plan", []) if isinstance(final_plan, dict) else final_plan

            for step in plan_steps:
                if step.get("action_type") == "tool_call":
                    params = step.get("parameters", {}) or {}
                    params = _inject_target_defaults(
                        params, tool_name=step.get("tool_name"), target_fqname=target_fqname
                    )
                    params = _resolve_sandbox_paths(params)
                    step["parameters"] = params

            log.info("[SCL] Phase 3: Executing %d approved steps.", len(plan_steps))
            # MODIFIED: Pass the `goal` to the execution loop for reflection context.
            execution_results = await self._execute_plan(plan_steps, runlog=runlog, goal=goal)

        # --- PHASE 4: REFLECT AND LEARN ---
        is_success = any(
            (v.get("status", "")).lower() in {"success", "ok", "passed", "proposed"}
            for v in execution_results.values()
            if isinstance(v, dict)
        )
        log.info("[SCL] Phase 4: Reflecting on turn outcome for learning.")

        scorer_results = await _run_utility_scorer(
            goal=goal,
            dossier=dossier,
            plan=final_plan,
            execution_results=execution_results,
            final_diff="",
            verification_results={},
            runlog=runlog,
        )
        utility_score = scorer_results.get("utility_score", 0.0)

        # LEARNING LOOP 1: If deliberation was successful, create a new synaptic trace.
        if not was_reflex and is_success and state_vector and utility_score > 0.7:
            try:
                new_trace = SynapticTrace(
                    triggering_state_vector=state_vector,
                    action_sequence=plan_steps,
                    outcome_utility=utility_score,
                    generation_timestamp=time.time(),
                )
                await self.trace_db.save(new_trace)
                log.info(
                    f"[SCL-S2] ✅ Synaptic Solidification: New reflex created: {new_trace.trace_id}"
                )
                runlog.log_note(
                    "synaptic_solidification",
                    {"trace_id": new_trace.trace_id, "utility": utility_score},
                )
            except Exception as e:
                log.error(f"[SCL-S2] Synaptic Solidification failed: {e!r}", exc_info=True)

        # LEARNING LOOP 2: If a reflex was used, reinforce it.
        if was_reflex and matching_trace:
            try:
                await self.trace_db.record_application(matching_trace.trace_id)
                arm_id_for_synapse = f"trace::{matching_trace.trace_id}"
                feedback = self.synapse.reward_arm if is_success else self.synapse.punish_arm
                await feedback(arm_id=arm_id_for_synapse, value=0.25)
                log.info(
                    f"[SCL-S1] {'👍 Rewarded' if is_success else '👎 Punished'} reflex: {matching_trace.trace_id}"
                )
                runlog.log_note(
                    "reflex_feedback",
                    {
                        "action": "reward" if is_success else "punish",
                        "trace_id": matching_trace.trace_id,
                    },
                )
            except Exception as e:
                log.error(f"[SCL-S1] Reflex reinforcement failed: {e!r}", exc_info=True)

        await self.blackboard.record_turn(
            goal=goal,
            plan=final_plan,
            execution_outcomes={k: v.get("status", "error") for k, v in execution_results.items()},
            utility_score=utility_score,
            utility_reasoning=scorer_results.get("reasoning", ""),
        )
        await self.blackboard.persist_to_memory()

        metrics = {
            "chosen_arm_id": final_plan.get("dynamic_plan_arm_id", "dyn::unknown"),
            "success": 1.0 if is_success else 0.0,
            "utility_score": utility_score,
        }
        if episode_id:
            await self.synapse.log_outcome(
                episode_id=episode_id,
                task_key="simula.agent.reflex" if was_reflex else "simula.agent.turn",
                metrics=metrics,
            )
            log.info(
                "[SCL] Logged outcome for episode '%s' with score %s.", episode_id, utility_score
            )

        runlog.log_outcome(
            status="ok" if is_success else "error",
            episode_id=episode_id,
            utility_score=utility_score,
            notes={"final_plan": final_plan, "tool_execution": execution_results},
        )
        runlog.save()

        return {
            "status": "ok" if is_success else "error",
            "episode_id": episode_id,
            "tool_execution": execution_results,
            "was_reflex": was_reflex,
        }

    # --- NEW METHOD: The "Chess Master" Reflection Step ---
    async def _reflect_and_revise_plan(
        self, goal: str, executed_step: dict, outcome: dict, remaining_steps: list[dict]
    ) -> list[dict]:
        """
        After a tool executes, this method makes a quick LLM call to decide if the plan is still valid.
        """
        log.info("[SCL] 🤔 Reflecting on last action's outcome...")
        try:
            prompt = await build_prompt(
                scope="simula.plan_reflector",
                context={
                    "goal": goal,
                    "executed_step": executed_step,
                    "outcome": outcome,
                    "remaining_steps": remaining_steps,
                },
                summary="Given the last outcome, decide to continue or revise the plan.",
            )
            # Use a fast, cheap model for this decision
            llm_policy = {"model": "gpt-4o-mini", "temperature": 0.1}
            response = await call_llm_service(
                prompt, agent_name="Simula.Reflector", policy_override=llm_policy
            )
            decision_obj = extract_json_flex(response.text)

            if decision_obj and decision_obj.get("decision") == "revise":
                new_plan = decision_obj.get("new_plan", [])
                if new_plan:
                    log.info("[SCL] ♟️ Plan revised mid-flight based on new information.")
                    return new_plan
        except Exception as e:
            log.warning(f"[SCL] Plan reflection step failed: {e!r}. Continuing with original plan.")

        # Default to continuing with the original plan
        return remaining_steps

    # --- REWRITTEN METHOD: The "Chess Master" Execution Loop ---
    async def _execute_plan(
        self, plan_steps: list[dict[str, Any]], runlog: RunLogger | None = None, goal: str = ""
    ) -> dict[str, Any]:
        """
        Executes a plan step-by-step, reflecting and potentially revising after each action.
        """
        results: dict[str, Any] = {}
        # Make a copy to safely modify the plan mid-execution
        current_plan = list(plan_steps)
        step_index = 0

        while step_index < len(current_plan):
            step = current_plan[step_index]
            step_key = f"step_{step_index}_{step.get('tool_name', 'unknown')}"

            if not isinstance(step, dict) or step.get("action_type") != "tool_call":
                step_index += 1
                continue

            tool_name = step.get("tool_name")
            if not tool_name:
                outcome = {"status": "error", "reason": "Missing tool_name in plan step."}
                results[step_key] = outcome
                if runlog:
                    runlog.log_tool_call(
                        index=step_index, tool_name="(missing)", parameters={}, outcome=outcome
                    )
                # A malformed plan is a critical failure, stop execution.
                break

            params = step.get("parameters", {}) or {}
            try:
                outcome = await dispatch_tool(f"simula.agent.{tool_name}", params)
            except Exception as e:
                outcome = {
                    "status": "error",
                    "reason": f"Tool '{tool_name}' crashed unexpectedly: {e!r}",
                }

            results[step_key] = outcome
            if runlog:
                runlog.log_tool_call(
                    index=step_index, tool_name=tool_name, parameters=params, outcome=outcome
                )

            # --- REFLECTION POINT ---
            # If the tool failed, stop immediately. The next turn will begin with this failure as context.
            if outcome.get("status") != "success":
                log.error(f"[SCL] Execution halted at step {step_index} due to tool failure.")
                break

            # If the tool succeeded, reflect on the outcome and see if the rest of the plan is still valid.
            remaining_steps = current_plan[step_index + 1 :]
            if remaining_steps:  # No need to reflect on the very last step
                revised_remaining_steps = await self._reflect_and_revise_plan(
                    goal=goal,
                    executed_step=step,
                    outcome=outcome,
                    remaining_steps=remaining_steps,
                )
                # Splice the revised plan back into the current execution
                current_plan = current_plan[: step_index + 1] + revised_remaining_steps

            step_index += 1

        return results
