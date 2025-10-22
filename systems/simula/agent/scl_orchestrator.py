# systems/simula/agent/scl_orchestrator.py
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from core.prompting.orchestrator import build_prompt
from core.services.qora import QoraClient
from core.services.synapse import SynapseClient
from core.utils.llm_gateway_client import call_llm_service_direct, extract_json_flex
from core.utils.net_api import ENDPOINTS, post_internal
from systems.simula.code_sim.telemetry import get_tracked_tools, resolve_tool
from systems.simula.memory.schemas import SynapticTrace
from systems.simula.memory.trace_db import TraceDBClient
from systems.synapse.schemas import TaskContext, ArmScore

from ._plan_contract import PlanSpec  # ✨ PlanSpec enforcement
from .deliberation import DeliberationRoom, _ensure_strategy_arm, FALLBACK_ARM_ID
from .dispatcher import dispatch_tool
from .runlog import RunLogger
from .scl_context import Blackboard, WorkingContext, synthesize_context
from .scl_utils import _run_utility_scorer

log = logging.getLogger(__name__)

# ==============================================================================
# Configuration & Constants
# ==============================================================================
EXCLUDED_PREFIXES: tuple[str, ...] = ("dyn::", "reflex::")  # reserved for future use
DEFAULT_MAX_STEPS = int(os.getenv("SIMULA_MAX_STEPS", "12"))
FAST_MODEL = os.getenv("SIMULA_FAST_MODEL", "gpt-4o-mini")
MAX_EVIDENCE_ITEMS = int(os.getenv("SIMULA_EVIDENCE_MAX_ITEMS", "16"))
MAX_EVIDENCE_BYTES = int(os.getenv("SIMULA_EVIDENCE_MAX_BYTES", "200_000"))


# ==============================================================================
# Data Structures & Helpers
# ==============================================================================
async def _kick_qora_reindex(*, decision_id: str, root: str = ".", base_rev: str | None = None):
    """
    Fire-and-forget Qora WM admin call using the ENDPOINTS alias pattern.
    Uses post_internal() to inherit default internal headers. Never raises.
    """
    if os.getenv("SIMULA_TRIGGER_REINDEX", "1").lower() not in ("1", "true", "yes", "on"):
        return

    if not decision_id:
        return

    headers = {"x-decision-id": decision_id}
    payload = {
        "action": "reindex",
        "root": root,
        "force": False,
        "dry_run": False,
        "base_rev": base_rev,
        "bypass_dedupe": False,
    }

    try:
        res = await post_internal(
            ENDPOINTS.QORA_WM_ADMIN,
            json=payload,
            headers=headers,
            timeout=15.0,
        )
        res.raise_for_status()
    except Exception as e:
        logging.getLogger(__name__).warning("[SCL] wm_admin reindex kick failed: %r", e)


def _short(obj: Any, limit: int = 120) -> str:
    """Creates a concise string representation of an object for logging."""
    try:
        s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    except Exception:
        s = str(obj)
    return (s[:limit] + "…") if len(s) > limit else s


@dataclass
class Budget:
    max_steps: int = DEFAULT_MAX_STEPS
    used_steps: int = 0

    def can_take_step(self) -> bool:
        return self.used_steps < self.max_steps

    def note_step(self):
        self.used_steps += 1


@dataclass
class Invariants:
    must: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)


class EvidenceCache:
    """Holds compact snippets to avoid prompt bloat."""

    def __init__(self):
        self.items: list[dict] = []
        self.total_bytes = 0

    def add(self, card: dict):
        blob = json.dumps(card, ensure_ascii=False)
        self.items.append(card)
        self.total_bytes += len(blob.encode("utf-8"))
        while len(self.items) > MAX_EVIDENCE_ITEMS or self.total_bytes > MAX_EVIDENCE_BYTES:
            old = self.items.pop(0)
            self.total_bytes = max(0, self.total_bytes - len(json.dumps(old).encode("utf-8")))

    def snapshot(self) -> list[dict]:
        return list(self.items)


# -------------------- PlanSpec adapters & guards --------------------
def _ensure_planspec(obj: Any) -> PlanSpec:
    """Coerce dict-like 'final_plan' to a PlanSpec (pydantic v2-safe)."""
    if isinstance(obj, PlanSpec):
        return obj
    if not isinstance(obj, dict):
        raise ValueError("Final plan is not a dict and cannot be parsed as PlanSpec.")
    try:
        return PlanSpec.model_validate(obj)
    except Exception as e:
        raise ValueError(f"Final plan did not match PlanSpec: {e!r}")


def _adapt_planspec_to_exec_steps(pspec: PlanSpec) -> list[dict]:
    """
    Convert PlanSpec.plan steps into dispatcher-ready {tool_name, parameters}.
    Tool resolution is dynamic: action_type must correspond to a registered tool
    name or one of its aliases.
    """
    registry = get_tracked_tools()
    exec_steps: list[dict] = []

    for step in pspec.plan:
        action = step.action_type
        tool_name = resolve_tool(action)
        if not tool_name:
            tool_name = action if action in registry else None
        if not tool_name:
            raise ValueError(f"Unsupported or unknown action_type: {action!r} (not in tool registry)")

        params: dict[str, Any] = {}
        if action == "read_file":
            if not step.path:
                raise ValueError("read_file requires 'path'.")
            params = {"path": step.path}

        elif action == "get_context_dossier":
            if not step.target_fqname:
                raise ValueError("get_context_dossier requires 'target_fqname'.")
            params = {"target_fqname": step.target_fqname, "intent": step.intent or "debug"}

        elif action == "apply_patch":
            # Already validated by PlanSpec
            params = {"patch": step.patch}

        elif action == "run_tests":
            if not step.paths:
                raise ValueError("run_tests requires 'paths' (string).")
            params = {"paths": step.paths}

        else:
            # Future expansion: pass through additional fields (minus action_type)
            params = step.model_dump(exclude_none=True)
            params.pop("action_type", None)

        exec_steps.append({"tool_name": tool_name, "parameters": params})

    return exec_steps


def _derive_allowed_tools_from_exec_steps(exec_steps: list[dict], registry_tools: dict[str, Any]) -> set[str]:
    """
    Build allowed tool set from steps ∩ tracked registry.
    Warn on any tool names not registered; execution will still attempt but reflection will not add them.
    """
    names_in_plan = [s.get("tool_name") for s in exec_steps if isinstance(s, dict)]
    registered = set(registry_tools.keys())
    allowed = {n for n in names_in_plan if n in registered}
    unknown = [n for n in names_in_plan if n and n not in registered]
    if unknown:
        log.warning("[SCL] Plan references unknown tools (not registered): %s", unknown)
    return allowed


# ==============================================================================
# SCL Orchestrator
# ==============================================================================
class SCL_Orchestrator:
    """
    Dynamic, budgeted, and feedback-driven SCL orchestrator. It uses a reflex arc
    for common problems and convenes a powerful multi-agent DeliberationRoom for
    novel tasks, logging granular feedback at every step to enable learning.
    """

    def __init__(self, session_id: str, synapse_client: SynapseClient | None = None):
        self.session_id = session_id or uuid4().hex
        self.synapse = synapse_client or SynapseClient()
        self.blackboard = Blackboard(session_id=self.session_id)
        self.deliberation_room = DeliberationRoom(
            synapse_client=self.synapse,
            max_rounds=int(os.getenv("SIMULA_DELIBERATION_MAX_ROUNDS", "3")),
            deliberation_budget=int(os.getenv("SIMULA_DELIBERATION_BUDGET", "5")),
        )
        self.trace_db = TraceDBClient()
        self.qora = QoraClient()
        self.full_tool_map = get_tracked_tools()
        self._virtual_tools = {"probe", "diagnose"}  # not in registry; reflection can insert
        log.info(f"[SCL] Initialized | session={self.session_id}")

    def _apply_context_lens(self, mode: str) -> list[dict[str, Any]]:
        """Filters the available tools based on the current context mode and adds signatures."""
        if not mode:
            mode = "general"
        lensed_tools: list[dict[str, Any]] = []
        for tool_name, meta in self.full_tool_map.items():
            tool_modes = meta.get("modes", ["general"])
            if mode in tool_modes or "general" in tool_modes:
                func = meta.get("func")
                try:
                    sig = f"{tool_name}{inspect.signature(func) if func else '()'}"
                except Exception:
                    sig = f"{tool_name}()"
                lensed_tools.append(
                    {
                        "name": tool_name,
                        "signature": str(sig),
                        "description": inspect.getdoc(func) or "No description.",
                    },
                )
        return lensed_tools

    async def _reflect_and_revise_plan(
        self,
        goal: str,
        executed_step: dict,
        outcome: dict,
        remaining_steps: list[dict],
        invariants: Invariants,
        budget: Budget,
        allowed_tools: set[str],
        evidence_cards: list[dict],
    ) -> list[dict]:
        """Decide whether to continue or revise the plan based on the last step's outcome."""
        try:
            prompt = await build_prompt(
                scope="simula.plan_reflector",
                context={
                    "goal": goal,
                    "executed_step": executed_step,
                    "outcome": outcome,
                    "remaining_steps": remaining_steps,
                    "invariants": invariants.__dict__,
                    "budget": budget.__dict__,
                    "allowed_tools": sorted(list(allowed_tools)),
                    "evidence_cards": evidence_cards,
                },
                summary="",  # spec carries instructions
            )
            prompt.provider_overrides = {"model": FAST_MODEL, "temperature": 0.2, "max_tokens": 400}
            response = await call_llm_service_direct(
                prompt, agent_name="Simula.Reflector", scope="simula.plan_reflector",
            )
            decision_obj = (
                response.json
                if isinstance(response.json, dict)
                else (extract_json_flex(getattr(response, "text", "") or "") or {})
            )

            action = (decision_obj.get("decision") or "continue").lower()
            if action == "continue":
                return remaining_steps
            if action in ("revise", "reorder", "insert"):
                log.info(f"[SCL/Execution] Reflector decided to '{action}'.")
                if action == "reorder" and isinstance(decision_obj.get("new_remaining"), list):
                    return decision_obj["new_remaining"]
                if action == "revise" and isinstance(decision_obj.get("new_plan"), list):
                    return decision_obj["new_plan"]
                if action == "insert":
                    insertion = decision_obj.get("micro_step", {})
                    tool = insertion.get("tool_name")
                    if (
                        isinstance(insertion, dict)
                        and insertion.get("action_type") == "tool_call"
                        and (tool in allowed_tools or tool in self._virtual_tools)
                    ):
                        return [insertion] + remaining_steps
        except Exception as e:
            log.warning(f"[SCL/Execution] Reflection failed; continuing plan as is. Err: {e!r}")
        return remaining_steps

    async def run(
        self,
        *,
        goal: str,
        dossier: dict,
        target_fqname: str | None,
        error_context: str | None = None,
    ) -> dict[str, Any]:
        run_id = uuid4().hex
        decision_id: str | None = None  # ensure it's always defined
        runlog = RunLogger(session_id=self.session_id, goal=goal, target_fqname=target_fqname)
        runlog.set_tag("goal_hash", runlog.stable_id(goal))
        log.info(f"[SCL] ▶ Run Start | run_id={run_id} goal='{_short(goal)}'")

        await self.blackboard.load_from_memory()

        execution_results: dict[str, Any] = {}
        final_pspec: PlanSpec | None = None
        episode_id: str | None = None
        state_vector: list[float] = []
        matching_trace = None
        was_reflex = False

        # ============================ Reflex Arc (S1) ============================
        runlog.phase("reflex", "start")
        try:
            # state_vector = await self._generate_triggering_state_vector(...)
            if state_vector:
                matching_trace = await self.trace_db.search(state_vector, min_confidence=0.9)
        except Exception as e:
            log.error(f"[SCL/Reflex] ✖ Reflex Arc search failed: {e!r}", exc_info=True)

        if matching_trace:
            was_reflex, episode_id = True, f"reflex_ep_{uuid4().hex}"
            decision_id = episode_id
            runlog.set_tag("was_reflex", True)
            log.info(f"[SCL/Reflex] ✓ Match found: {matching_trace.trace_id}")
            # Reflex traces currently store dispatcher-style steps; no PlanSpec here.
            exec_steps = matching_trace.action_sequence
            allowed_tools = _derive_allowed_tools_from_exec_steps(exec_steps, self.full_tool_map)
        else:
            runlog.phase("reflex", "end", note="no_match")

            # ============================ Deliberation (S2) ======================
            runlog.phase("deliberation", "start")
            task_ctx = TaskContext(
                task_key="simula.agent.turn", goal=goal, metadata={"target_fqname": target_fqname},
            )

            working_context: WorkingContext | None = None
            exec_steps: list[dict] = []
            allowed_tools: set[str] = set()

            try:
                try:
                    selection = await self.synapse.select_or_plan(task_ctx, candidates=[])
                    episode_id = selection.episode_id
                    decision_id = episode_id
                    runlog.set_tag("episode_id", episode_id)

                    champion_arm = selection.champion_arm
                    # Ensure we always have a concrete arm id (guard unknown/empty)
                    working_context = await synthesize_context(
                        strategy_arm=champion_arm,
                        goal=goal,
                        target_fqname=target_fqname,
                        dossier=dossier,
                        blackboard=self.blackboard,
                        lensed_tools=self._apply_context_lens(
                            (champion_arm.policy_graph_meta or {}).get("mode", "simula_planful")
                        ),
                    )
                except Exception as e:
                    log.error(f"[SCL] Synapse selection failed, using fallback arm: {e!r}")
                    # Fallback working context with a safe arm id
                    fallback_arm = ArmScore(arm_id=FALLBACK_ARM_ID, score=0.0, meta={"source": "fallback_select"})
                    working_context = await synthesize_context(
                        strategy_arm=fallback_arm,
                        goal=goal,
                        target_fqname=target_fqname,
                        dossier=dossier,
                        blackboard=self.blackboard,
                        lensed_tools=self._apply_context_lens("simula_planful"),
                    )

                # Harden strategy arm on the context (registers, tags, etc.)
                await _ensure_strategy_arm(working_context, runlog=runlog)

                # Let the DeliberationRoom do its thing (it also promotes synth strategy ids → arms)
                champion_arm_mode = (getattr(working_context.strategy_arm, "policy_graph_meta", None) or {}).get(
                    "mode", "simula_planful"
                )
                deliberation_result = await self.deliberation_room.deliberate(
                    working_context=working_context,
                    episode_id=episode_id or f"ep_{uuid4().hex}",
                    runlog=runlog,
                    mode=champion_arm_mode,
                )

                if deliberation_result.status != "approved":
                    raise RuntimeError(
                        f"Plan rejected by DeliberationRoom: {deliberation_result.reason}",
                    )

                # 🔒 Validate the plan against PlanSpec
                final_pspec = _ensure_planspec(deliberation_result.final_plan)

                # Normalize into dispatcher steps
                exec_steps = _adapt_planspec_to_exec_steps(final_pspec)

                allowed_tools = _derive_allowed_tools_from_exec_steps(exec_steps, self.full_tool_map)
                if not allowed_tools:
                    log.warning("[SCL] No allowed tools derived from plan; execution may no-op.")

                runlog.phase("deliberation", "ok")

            except Exception as e:
                log.error(f"[SCL/Deliberation] ✖ Deliberation Core CRASHED: {e!r}", exc_info=True)
                if episode_id:
                    await self.synapse.log_outcome(
                        episode_id=episode_id,
                        task_key="simula.agent.turn",
                        metrics={"success": 0.0, "utility_score": 0.0, "reason": str(e)},
                    )
                return {"status": "error", "reason": f"Deliberation Core crashed: {e!r}"}

        # ============================ Execution ============================
        if not exec_steps:
            log.warning("[SCL] ✖ No steps to execute. Ending run.")
            return {"status": "error", "reason": "Deliberation produced an empty plan."}

        # Budget / invariants (fallback defaults if not present in older traces)
        budget = Budget()
        invariants = Invariants()

        runlog.phase("execution", "start")
        execution_results = await self._execute_plan(
            exec_steps=exec_steps,
            allowed_tools=allowed_tools,
            invariants=invariants,
            budget=budget,
            runlog=runlog,
            goal=goal,
            episode_id_hint=episode_id or f"ep_{uuid4().hex}",
        )
        runlog.phase("execution", "end")

        # ============================ Learning ============================
        runlog.phase("learning", "start")
        is_success = any(
            (v.get("status", "")).lower() == "success"
            for v in execution_results.values()
            if isinstance(v, dict)
        )
        # Provide the original PlanSpec object (if any) for richer scoring context
        scorer_results = await _run_utility_scorer(
            goal=goal,
            plan=final_pspec.model_dump() if isinstance(final_pspec, PlanSpec) else {"plan": exec_steps},  # type: ignore[attr-defined]
            execution_results=execution_results,
            runlog=runlog,
        )
        utility_score = scorer_results.get("utility_score", 0.0)
        log.info(
            f"[SCL] ✓ Run End | status={'OK' if is_success else 'ERROR'} utility={utility_score:.2f}",
        )

        # --- Final Outcome Logging to Synapse ---
        if episode_id:
            # Prefer the concrete strategy_id from the PlanSpec; fall back to working_context arm id; then a safe fallback
            chosen_arm_id = (
                getattr(final_pspec, "strategy_id", None)
                or (getattr(getattr(working_context, "strategy_arm", None), "arm_id", None) if not was_reflex else None)
                or ("reflex::unknown" if was_reflex else FALLBACK_ARM_ID)
            )
            metrics = {
                "chosen_arm_id": chosen_arm_id,
                "success": 1.0 if is_success else 0.0,
                "utility_score": utility_score,
                "steps_executed": len(execution_results),
            }
            await self.synapse.log_outcome(
                episode_id=episode_id,
                task_key="simula.agent.reflex" if was_reflex else "simula.agent.turn",
                metrics=metrics,
            )

        # Solidify reflex trace only when applicable
        if was_reflex is False and is_success and (state_vector) and utility_score > 0.8:
            try:
                new_trace = SynapticTrace(
                    triggering_state_vector=state_vector,
                    action_sequence=exec_steps,
                    outcome_utility=utility_score,
                )
                await self.trace_db.save(new_trace)
                log.info(f"[SCL/Learning] ✅ Synaptic trace solidified | trace={new_trace.trace_id}")
            except Exception as e:
                log.error(f"[SCL/Learning] ✖ Synaptic solidification failed: {e!r}")

        # --- Always close the runlog; schedule reindex if SUCCESS ---
        runlog.phase("learning", "end")
        runlog.save()

        if is_success:
            try:
                decision_id = decision_id or episode_id or f"ep_{uuid4().hex}"
                asyncio.create_task(
                    _kick_qora_reindex(
                        decision_id=decision_id,
                        root=os.getenv("QORA_REPO_ROOT", "."),
                        base_rev=None,
                    ),
                )
            except Exception as e:
                log.warning("[SCL] failed to schedule wm_admin reindex: %r", e)

        return {"status": "ok" if is_success else "error", "episode_id": episode_id}

    async def _execute_plan(
        self,
        *,
        exec_steps: list[dict],
        allowed_tools: set[str],
        invariants: Invariants,
        budget: Budget,
        runlog: RunLogger,
        goal: str,
        episode_id_hint: str,
    ) -> dict[str, Any]:
        results, evidence = {}, EvidenceCache()
        current_plan = list(exec_steps)
        step_index = 0
        log.info(f"[SCL/Execution] ▶ Starting plan execution | steps={len(current_plan)}")

        while step_index < len(current_plan):
            if not budget.can_take_step():
                log.warning("[SCL/Execution] ✖ Budget exceeded.")
                break

            step = current_plan[step_index]
            tool_name = (step.get("tool_name") or "").strip()
            if not tool_name:
                step_index += 1
                continue

            # Tool gating: reflection can add virtual micro-steps; otherwise enforce allow-list
            if tool_name not in allowed_tools and tool_name not in self._virtual_tools:
                log.warning("[SCL/Execution] Skipping unapproved tool '%s'", tool_name)
                step_index += 1
                continue

            log.info(
                f"[SCL/Execution] ▶ Step {step_index + 1}/{len(current_plan)}: Running tool '{tool_name}'",
            )
            budget.note_step()
            params = step.get("parameters", {}) or {}

            try:
                outcome = await dispatch_tool(f"simula.agent.{tool_name}", params)
            except Exception as e:
                outcome = {
                    "status": "error",
                    "reason": f"Tool '{tool_name}' crashed unexpectedly: {e!r}",
                }

            results[f"step_{step_index}"] = outcome
            if runlog:
                runlog.log_tool_call(
                    index=step_index, tool_name=tool_name, parameters=params, outcome=outcome,
                )

            # --- Per-Step Feedback Loop ---
            step_success = (outcome.get("status") or "").lower() == "success"
            asyncio.create_task(
                self.synapse.log_outcome(
                    episode_id=episode_id_hint,
                    task_key=f"simula.agent.tool.{tool_name}",
                    metrics={"success": 1.0 if step_success else 0.0},
                ),
            )

            if not step_success:
                log.error(f"[SCL/Execution] ✖ Step failed: {_short(outcome.get('reason'))}")

                # Attempt a one-shot repair via Synapse (best-effort)
                try:
                    repair = await self.synapse.repair_skill_step(
                        episode_id=episode_id_hint,
                        failed_step_index=step_index,
                        error_observation=outcome,
                    )
                    if repair and getattr(repair, "micro_step", None):
                        micro = repair.micro_step
                        m_tool = (micro.get("tool_name") or "").strip()
                        if m_tool and (m_tool in allowed_tools or m_tool in self._virtual_tools):
                            log.info(
                                "[SCL/Execution] Repair suggested; inserting micro-step '%s'.",
                                m_tool,
                            )
                            current_plan = (
                                current_plan[: step_index + 1]
                                + [micro]
                                + current_plan[step_index + 1 :]
                            )
                            # Do not advance index; run the inserted step next.
                            continue
                except Exception as e:
                    log.warning(f"[SCL/Execution] Repair attempt failed: {e!r}")

                # If no repair step could be inserted, break hard.
                break

            # Cache any compact evidence card for downstream reflection
            if isinstance(outcome.get("evidence_card"), dict):
                evidence.add(outcome["evidence_card"])

            # Ask the Referee whether to continue or revise the rest of the plan
            remaining_steps = current_plan[step_index + 1 :]
            if remaining_steps:
                revised_remaining = await self._reflect_and_revise_plan(
                    goal=goal,
                    executed_step=step,
                    outcome=outcome,
                    remaining_steps=remaining_steps,
                    invariants=invariants,
                    budget=budget,
                    allowed_tools=allowed_tools,
                    evidence_cards=evidence.snapshot(),
                )
                if revised_remaining is not remaining_steps:
                    # Replace tail with reflector's suggestion
                    current_plan = current_plan[: step_index + 1] + revised_remaining

            step_index += 1

        log.info(f"[SCL/Execution] ✓ Finished plan execution | steps_run={step_index}")
        return results
