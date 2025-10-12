# systems/synapse/deliberation.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service, extract_json_flex
from systems.simula.agent.runlog import RunLogger

# FIXED: Corrected imports to point to their actual location in the simula.agent module
from systems.simula.agent.scl_context import WorkingContext
from systems.simula.agent.scl_utils import (
    _coerce_plan_steps,
    _sha16_for,
    register_dynamic_arm_in_graph,
)
from systems.synapse.schemas import ArmScore

log = logging.getLogger(__name__)


class DeliberationResult(BaseModel):
    """Standardized output for the deliberation process."""

    status: str = "rejected"  # "approved", "rejected"
    reason: str = "No deliberation occurred."
    initial_plan: dict[str, Any] = Field(default_factory=dict)
    critique: dict[str, Any] = Field(default_factory=dict)
    final_plan: dict[str, Any] = Field(default_factory=dict)


class DeliberationRoom:
    """Orchestrates a multi-agent deliberation process to create a robust plan for Simula."""

    def __init__(self) -> None:
        self._mode: str = "general"  # carried across a single deliberation, harmless default

    async def deliberate(
        self,
        *,
        working_context: WorkingContext,
        runlog: RunLogger | None = None,
        mode: str | None = None,
    ) -> DeliberationResult:
        """Runs the full deliberation cycle: Plan -> Critique -> Judge."""
        # cache the mode for this deliberation; exposed via _prepare_context()
        if mode:
            self._mode = mode

        # ---------------- PLAN ----------------
        try:
            initial_plan_obj = await self._invoke_planner(working_context, runlog=runlog)
            if not isinstance(initial_plan_obj, dict) or not initial_plan_obj.get("plan"):
                return DeliberationResult(
                    status="rejected",
                    reason="Planner failed to generate a valid initial plan structure.",
                )
        except Exception as e:
            log.error("[Deliberation] Planner agent failed: %r", e, exc_info=True)
            return DeliberationResult(status="rejected", reason=f"Planner agent crashed: {e}")

        # --------------- CRITIQUE --------------
        try:
            critique_obj = await self._invoke_red_team(
                working_context, initial_plan_obj, runlog=runlog
            )
            if not isinstance(critique_obj, dict):
                critique_obj = {"summary": "Red-Team returned invalid format.", "findings": []}
        except Exception as e:
            log.error("[Deliberation] Red-Team agent failed: %r", e, exc_info=True)
            critique_obj = {"summary": f"Red-Team agent crashed: {e}", "findings": []}

        # ---------------- JUDGE ----------------
        try:
            judgement_obj = await self._invoke_judge(
                working_context,
                initial_plan_obj,
                critique_obj,
                runlog=runlog,
            )
            if not isinstance(judgement_obj, dict):
                return DeliberationResult(
                    status="rejected",
                    reason="Judge agent returned an invalid format.",
                    initial_plan=initial_plan_obj,
                    critique=critique_obj,
                )

            decision = (judgement_obj.get("decision") or "reject").lower()
            reason = judgement_obj.get("reasoning") or "No reasoning provided."

            if decision == "approve":
                final_plan = self._normalize_and_finalize_plan(
                    initial_plan_obj,
                    working_context.strategy_arm,
                    runlog=runlog,
                )
                return DeliberationResult(
                    status="approved",
                    reason=reason,
                    initial_plan=initial_plan_obj,
                    critique=critique_obj,
                    final_plan=final_plan,
                )

            elif decision == "revise":
                revised_plan_obj = judgement_obj.get("revised_plan", {})
                # Accept dict-with-plan OR a non-empty list
                is_valid_plan = (
                    isinstance(revised_plan_obj, dict) and revised_plan_obj.get("plan")
                ) or (isinstance(revised_plan_obj, list) and len(revised_plan_obj) > 0)
                if not is_valid_plan:
                    return DeliberationResult(
                        status="rejected",
                        reason="Judge's revised plan was invalid or empty.",
                        initial_plan=initial_plan_obj,
                        critique=critique_obj,
                    )

                final_plan = self._normalize_and_finalize_plan(
                    revised_plan_obj,
                    working_context.strategy_arm,
                    runlog=runlog,
                )
                return DeliberationResult(
                    status="approved",
                    reason=reason,
                    initial_plan=initial_plan_obj,
                    critique=critique_obj,
                    final_plan=final_plan,
                )

            # default: REJECT
            return DeliberationResult(
                status="rejected",
                reason=reason,
                initial_plan=initial_plan_obj,
                critique=critique_obj,
            )

        except Exception as e:
            log.error("[Deliberation] Judge agent failed: %r", e, exc_info=True)
            return DeliberationResult(
                status="rejected",
                reason=f"Judge agent crashed: {e}",
                initial_plan=initial_plan_obj,
                critique=critique_obj,
            )

    # ----------------------------- helpers -----------------------------

    def _prepare_context(self, context: WorkingContext) -> dict[str, Any]:
        """
        Flatten + sanitize for Jinja. Ensure 'strategy_arm' is ALWAYS present
        as a dict so templates can do {{ strategy_arm.arm_id }} safely.
        """
        out: dict[str, Any] = {
            "goal": context.goal,
            "target_fqname": context.target_fqname,
            "history_summary": context.history_summary,
            "blackboard_insights": dict(getattr(context, "blackboard_insights", {}) or {}),
            "file_cards": [fc.model_dump(mode="json") for fc in (context.file_cards or [])],
            "tool_hints": [th.model_dump(mode="json") for th in (context.tool_hints or [])],
            "extras": getattr(context, "extras", {}) or {},
            "context_vars": getattr(context, "context_vars", {}) or {},
            # expose the selected mode for templates/agents
            "mode": getattr(self, "_mode", "general"),
        }
        # Harden strategy_arm
        sa: dict[str, Any] = {"arm_id": "unknown", "reason": "not provided", "score": 0.0}
        try:
            if isinstance(context.strategy_arm, ArmScore):
                sa = context.strategy_arm.model_dump(mode="json")
            elif isinstance(context.strategy_arm, dict):
                sa = {
                    "arm_id": context.strategy_arm.get("arm_id", "unknown"),
                    **context.strategy_arm,
                }
            elif isinstance(context.strategy_arm, str):
                sa = {"arm_id": context.strategy_arm}
        except Exception:
            pass
        out["strategy_arm"] = sa
        out["strategy_arm_id"] = sa.get("arm_id", "unknown")
        return out

    async def _invoke_planner(
        self, context: WorkingContext, runlog: RunLogger | None
    ) -> dict[str, Any]:
        prompt_context = self._prepare_context(context)
        prompt = await build_prompt(
            scope="simula.deliberation.planner",
            context=prompt_context,
            summary="Generate a plan based on the given strategy.",
        )
        resp = await call_llm_service(
            prompt,
            agent_name="Simula.Planner",
            scope="simula.deliberation.planner",
            timeout=45.0,
        )
        text = getattr(resp, "text", "")
        plan = extract_json_flex(text) or {}
        if not isinstance(plan, dict):
            plan = {}

        if runlog:
            preview = None
            try:
                preview = getattr(prompt, "text", None)
                if not preview and hasattr(prompt, "messages"):
                    msgs = getattr(prompt, "messages", [])
                    preview = msgs[-1]["content"] if msgs else None
            except Exception:
                pass
            runlog.log_llm(
                phase="planner",
                scope="simula.deliberation.planner",
                agent="Simula.Planner",
                prompt_preview=preview,
                prompt_struct=getattr(prompt, "model_dump", lambda **_: None)()
                if hasattr(prompt, "model_dump")
                else None,
                completion_text=text,
                extra={"plan_keys": list(plan.keys()) if isinstance(plan, dict) else []},
            )
        return plan

    async def _invoke_red_team(
        self, context: WorkingContext, plan_to_critique: dict[str, Any], runlog: RunLogger | None
    ) -> dict[str, Any]:
        prompt_context = self._prepare_context(context)
        prompt_context["plan_to_critique"] = plan_to_critique
        prompt = await build_prompt(
            scope="simula.deliberation.red_team",
            context=prompt_context,
            summary="Find all flaws in the proposed plan.",
        )
        resp = await call_llm_service(
            prompt,
            agent_name="Simula.RedTeam",
            scope="simula.deliberation.red_team",
            timeout=45.0,
        )
        text = getattr(resp, "text", "")
        critique = extract_json_flex(text) or {}
        if not isinstance(critique, dict):
            critique = {}

        if runlog:
            preview = None
            try:
                preview = getattr(prompt, "text", None)
                if not preview and hasattr(prompt, "messages"):
                    msgs = getattr(prompt, "messages", [])
                    preview = msgs[-1]["content"] if msgs else None
            except Exception:
                pass
            runlog.log_llm(
                phase="red_team",
                scope="simula.deliberation.red_team",
                agent="Simula.RedTeam",
                prompt_preview=preview,
                prompt_struct=getattr(prompt, "model_dump", lambda **_: None)()
                if hasattr(prompt, "model_dump")
                else None,
                completion_text=text,
                extra={
                    "findings_len": len(critique.get("findings", []))
                    if isinstance(critique, dict)
                    else 0
                },
            )
        return critique

    async def _invoke_judge(
        self,
        context: WorkingContext,
        plan: dict[str, Any],
        critique: dict[str, Any],
        runlog: RunLogger | None,
    ) -> dict[str, Any]:
        prompt_context = self._prepare_context(context)
        prompt_context["initial_plan"] = plan
        prompt_context["critique"] = critique
        prompt = await build_prompt(
            scope="simula.deliberation.judge",
            context=prompt_context,
            summary="Decide whether to approve, revise, or reject the plan.",
        )
        resp = await call_llm_service(
            prompt,
            agent_name="Simula.Judge",
            scope="simula.deliberation.judge",
            timeout=90.0,  # judge often needs more time
        )
        text = getattr(resp, "text", "")
        judgement = extract_json_flex(text) or {}
        if not isinstance(judgement, dict):
            judgement = {}

        if runlog:
            preview = None
            try:
                preview = getattr(prompt, "text", None)
                if not preview and hasattr(prompt, "messages"):
                    msgs = getattr(prompt, "messages", [])
                    preview = msgs[-1]["content"] if msgs else None
            except Exception:
                pass
            runlog.log_llm(
                phase="judge",
                scope="simula.deliberation.judge",
                agent="Simula.Judge",
                prompt_preview=preview,
                prompt_struct=getattr(prompt, "model_dump", lambda **_: None)()
                if hasattr(prompt, "model_dump")
                else None,
                completion_text=text,
                extra={"decision": judgement.get("decision")},
            )
        return judgement

    def _normalize_and_finalize_plan(
        self, plan_obj: dict[str, Any], champion_arm: ArmScore, runlog: RunLogger | None
    ) -> dict[str, Any]:
        """
        Ensures the final plan has a canonical structure.

        IMPORTANT:
        - Do NOT overwrite the base/champion arm with the dynamic plan handle.
        - Provide both IDs explicitly (base + dynamic).
        """
        plan_steps = plan_obj if isinstance(plan_obj, list) else plan_obj.get("plan", [])

        normalized = {
            "interim_thought": (
                plan_obj.get("interim_thought", "No thought provided.")
                if isinstance(plan_obj, dict)
                else "No thought provided."
            ).strip(),
            "scratchpad": (
                plan_obj.get("scratchpad", "No scratchpad provided.")
                if isinstance(plan_obj, dict)
                else "No scratchpad provided."
            ).strip(),
            "plan": _coerce_plan_steps(plan_steps),
            "final_synthesis_prompt": (
                plan_obj.get("final_synthesis_prompt", "Summarize the results.")
                if isinstance(plan_obj, dict)
                else "Summarize the results."
            ).strip(),
        }

        try:
            base_arm_id = champion_arm.arm_id
        except Exception:
            base_arm_id = "unknown"

        hash_seed = {
            "base_arm": base_arm_id,
            "plan": {
                "interim_thought": normalized["interim_thought"],
                "scratchpad": normalized["scratchpad"],
                "plan": normalized["plan"],
                "final_synthesis_prompt": normalized["final_synthesis_prompt"],
            },
        }
        dyn_hash = _sha16_for(hash_seed)
        dyn_arm_id = f"dyn::{dyn_hash}"

        normalized["champion_arm_id"] = base_arm_id
        normalized["dynamic_plan_arm_id"] = dyn_arm_id

        log.info(
            "[Deliberation] Finalized plan with base_arm=%s dynamic_arm=%s steps=%d",
            base_arm_id,
            dyn_arm_id,
            len(normalized["plan"]),
        )

        asyncio.create_task(register_dynamic_arm_in_graph(dyn_arm_id, "simula_planful"))

        if runlog:
            runlog.log_llm(
                phase="plan_finalize",
                scope="simula.deliberation.finalize",
                agent="Simula.DeliberationRoom",
                prompt_preview="(normalized plan summary)",
                prompt_struct=None,
                completion_text=f"base_arm={base_arm_id}, dynamic_arm={dyn_arm_id}, steps={len(normalized['plan'])}",
                extra={
                    "step_kinds": [
                        s.get("action_type") for s in normalized["plan"] if isinstance(s, dict)
                    ]
                },
            )

        return normalized
