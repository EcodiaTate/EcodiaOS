# systems/simula/agent/deliberation.py
from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from core.prompting.orchestrator import build_prompt
from core.services.synapse import SynapseClient
from core.utils.llm_gateway_client import (
    call_llm_service_direct,
    extract_json_flex,
)
from systems.simula.agent.runlog import RunLogger
from systems.simula.agent.scl_context import WorkingContext
from systems.simula.agent.scl_utils import (
    _sha16_for,
    register_dynamic_arm_in_graph,
)
from systems.synapse.schemas import ArmScore

# Plan contract (schema)
from ._plan_contract import PlanSpec

log = logging.getLogger(__name__)

# ==============================================================================
# Models & small helpers
# ==============================================================================

def _short(obj: Any, limit: int = 400) -> str:
    """Creates a concise string representation of an object for logging."""
    try:
        s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    except Exception:
        s = str(obj)
    return (s[:limit] + "…") if len(s) > limit else s


class DeliberationResult(BaseModel):
    """Standardized output for the deliberation process."""
    status: str = "rejected"
    reason: str = "No deliberation occurred."
    initial_plan: dict[str, Any] = Field(default_factory=dict)
    final_plan: dict[str, Any] = Field(default_factory=dict)


def _safe_arm_id(obj: Any, default: str = "unknown") -> str:
    """Safely extracts an arm_id from various object types."""
    if isinstance(obj, ArmScore):
        return obj.arm_id or default
    if isinstance(obj, dict):
        return obj.get("arm_id", default)
    if isinstance(obj, str):
        return obj or default
    return default


def _cap_context(ctx: WorkingContext) -> dict[str, Any]:
    """Compact, prompt-friendly context with sane fallbacks."""
    return {
        "goal": ctx.goal,
        "target_fqname": ctx.target_fqname,
        "history_summary": (getattr(ctx, "history_summary", "") or "")[:1200],
        # NOTE: these are action-type names that PlanSpec uses; keep aligned with your tool map.
        "allowed_tools": list(getattr(ctx, "allowed_tools", None) or ["read_file", "get_context_dossier", "apply_patch", "run_tests"]),
        "write_scope_paths": list(getattr(ctx, "write_scope_paths", None) or ["tests/**", "src/**"]),
        "forbidden_paths": list(getattr(ctx, "forbidden_paths", None) or [".git/**", "node_modules/**"]),
        "required_verification_types": list(getattr(ctx, "required_verification_types", None) or ["unit"]),
        "default_rollback": getattr(ctx, "default_rollback", None) or "git checkout -- <file>",
        "strategy_arm_id": _safe_arm_id(getattr(ctx, "strategy_arm", None)),
    }


# ==============================================================================
# Strategy / Arm wiring guards
# ==============================================================================

FALLBACK_ARM_ID = "simula.base.safe_fallback.v1"

def _needs_fallback_arm(arm_id: str | None) -> bool:
    return not arm_id or arm_id.strip().lower() in {"", "unknown", "base.safe_fallback", "safe_fallback", "none"}

async def _ensure_strategy_arm(ctx: WorkingContext, runlog: RunLogger | None = None) -> None:
    """
    Ensure WorkingContext has a concrete arm id and it is registered in the graph.
    """
    if not hasattr(ctx, "strategy_arm") or ctx.strategy_arm is None:
        ctx.strategy_arm = ArmScore(arm_id=FALLBACK_ARM_ID, score=0.0, meta={"source": "fallback"})
        if runlog:
            runlog.set_tag("strategy_arm_source", "fallback_no_arm_object")
    arm_id = _safe_arm_id(ctx.strategy_arm)
    if _needs_fallback_arm(arm_id):
        ctx.strategy_arm.arm_id = FALLBACK_ARM_ID
        if runlog:
            runlog.set_tag("strategy_arm_source", "fallback_unknown_or_empty")
    # Register (best-effort)
    try:
        asyncio.create_task(register_dynamic_arm_in_graph(ctx.strategy_arm.arm_id, family="simula.base"))
    except Exception as e:
        log.warning("[Deliberation] Arm registration best-effort failed: %r", e)
    if runlog:
        runlog.set_tag("strategy_arm", ctx.strategy_arm.arm_id)
# In systems/simula/agent/deliberation.py

async def _promote_synth_strategy(ctx: WorkingContext, synth_result: dict, runlog: RunLogger | None = None) -> None:
    """
    If the synthesizer yields a strategy_id, promote it to the current strategy_arm, register it,
    and keep runlog hints for observability.
    """
    sid = (synth_result or {}).get("strategy_id")
    if not sid:
        return
    # Normalize to a concrete namespace if needed
    if not sid.startswith("simula."):
        sid = f"simula.{sid}"
    if not sid.endswith(".v1"):
        sid = f"{sid}.v1"
    # Apply
    prev = _safe_arm_id(getattr(ctx, "strategy_arm", None))
    if not hasattr(ctx, "strategy_arm") or ctx.strategy_arm is None:
        # This path likely needs the 'reason' field as well for consistency.
        ctx.strategy_arm = ArmScore(
            arm_id=sid,
            score=0.0,
            reason="Initial arm promotion from synthesizer.",
            meta={"source": "synth_promotion"}
        )
    else:
        original_score = getattr(ctx.strategy_arm, 'score', 0.0)
        ctx.strategy_arm = ArmScore(
            arm_id=sid,
            score=original_score,
            # --- FIX: Add the required 'reason' field ---
            reason="Promoted from synthesizer's output based on moderator feedback.",
            meta={"source": "synth_promotion"}
        )

    # Register
    try:
        asyncio.create_task(register_dynamic_arm_in_graph(sid, family="simula.base"))
    except Exception as e:
        log.warning("[Deliberation] Synth arm registration best-effort failed: %r", e)
    if runlog:
        runlog.set_tag("strategy_arm_prev", prev)
        runlog.set_tag("strategy_arm", sid)
        runlog.set_tag("strategy_arm_source", "synth_promotion")


# ==============================================================================
# Deterministic Gatekeeper (schema + scope + safety)
# ==============================================================================

def _diff_touched_paths(unified_diff: str) -> list[str]:
    """
    Extract file paths touched by a unified diff. We conservatively look at
    '+++ ' and '--- ' headers and return normalized paths (no a/ b/ prefixes).
    """
    touched: list[str] = []
    for line in unified_diff.splitlines():
        if line.startswith(("+++", "---")):
            parts = line.split()
            if len(parts) >= 2:
                path = parts[1]
                path = re.sub(r"^[ab]/", "", path)  # strip a/ or b/
                if path != "/dev/null" and path not in touched:
                    touched.append(path)
    return touched


def _paths_within_scope(paths: list[str], scope_globs: list[str]) -> bool:
    """True iff every path matches at least one allowed scope glob."""
    for p in paths:
        if not any(fnmatch.fnmatch(p, g) for g in scope_globs):
            return False
    return True


def _paths_violate_forbidden(paths: list[str], forbidden_globs: list[str]) -> bool:
    """True if any path matches a forbidden glob."""
    for p in paths:
        if any(fnmatch.fnmatch(p, g) for g in forbidden_globs):
            return True
    return False


def _has_required_verification_types(checks: list[dict], required: list[str]) -> bool:
    present = {(c.get("type") or "").lower() for c in checks if isinstance(c, dict)}
    return all(t.lower() in present for t in required)


def _gatekeep_contract(
    raw_plan_dict: dict,
    *,
    strategy_arm_id: str,
    allowed_tools: list[str],
    write_scope_paths: list[str],
    forbidden_paths: list[str],
    required_verification_types: list[str],
) -> tuple[bool, str, PlanSpec | None]:
    """
    Deterministic validation:
      1) Pydantic PlanSpec validation
      2) strategy_id exact match
      3) step action_types ⊆ allowed_tools
      4) apply_patch diffs only touch write_scope_paths and do not touch forbidden_paths
      5) verification_checks include required types
    """
    try:
        spec = PlanSpec.model_validate(raw_plan_dict)
    except ValidationError as e:
        return False, f"schema_validation_error: {e}", None

    # 2) strategy id must match the selected arm
    if (spec.strategy_id or "").strip() != (strategy_arm_id or "").strip():
        return False, "strategy_id_mismatch: plan.strategy_id != selected arm id", None

    # 3) allowed action types only
    allowed_action_types = set(allowed_tools or [])
    for step in spec.plan:
        step_type = step.action_type
        if step_type not in allowed_action_types:
            return False, f"forbidden_action: {step_type} not in allowed_tools", None

    # 4) patch scope checks
    for step in spec.plan:
        if step.action_type == "apply_patch":
            diff = step.patch or ""
            paths = _diff_touched_paths(diff)
            if not paths:
                return False, "invalid_patch: no file headers found in diff", None
            if _paths_violate_forbidden(paths, forbidden_paths):
                return False, f"forbidden_paths_touched: {paths}", None
            if not _paths_within_scope(paths, write_scope_paths):
                return False, f"out_of_scope_paths: {paths}", None

    # 5) verification checks coverage
    if not _has_required_verification_types(
        [c.model_dump() for c in spec.verification_checks], required_verification_types,
    ):
        return False, "insufficient_verification_checks", None

    return True, "ok", spec


# ==============================================================================
# LLM Auditors (soft)
# ==============================================================================

SECONDARY_AUDITORS = [
    "Simula.SecurityAuditor",
    "Simula.TypeHygieneAuditor",
    "Simula.GoalObedienceAuditor",
    "Simula.ImportAuditor",
    "Simula.RedTeamAuditor",
]

async def _audit_secondary_llm(plan_json: dict) -> tuple[bool, str]:
    """
    Optional soft audits. Never override deterministic gatekeeping.
    Returns False on first explicit rejection.
    """
    for agent in SECONDARY_AUDITORS:
        prompt = {
            "role": "user",
            "content": (
                "Audit this structured plan JSON for safety, import correctness, goal adherence, "
                'and type hygiene. Return ONLY JSON {"approved": true|false, "reason": "..."}.'
            ),
        }
        try:
            res = await call_llm_service_direct(
                prompt=prompt, agent_name=agent, scope="simula.deliberation.auditor",
            )
            obj = extract_json_flex(getattr(res, "text", "")) or {}
            if not obj.get("approved"):
                reason = obj.get("reason") or f"{agent} rejection"
                return False, reason
        except Exception as e:
            # Non-fatal: if an auditor fails, continue others.
            log.warning("[Deliberation] Auditor %s failed: %r", agent, e)
    return True, "all secondary auditors approved"


# ==============================================================================
# DeliberationRoom
# ==============================================================================

def _balance_trim(s: str) -> str:
    # Trim to last full closing brace if we can detect obvious truncation
    last = max(s.rfind("}"), s.rfind("]"))
    return s[: last + 1] if last != -1 else s

def _salvage_json(text: str) -> dict | None:
    try:
        from json import loads
        candidate = _balance_trim(text.strip())
        # Common case: content starts with prose then JSON. Slice first '{'
        if "{" in candidate:
            candidate = candidate[candidate.find("{") :]
        return loads(candidate)
    except Exception:
        return None


class DeliberationRoom:
    """
    Multi-hypothesis deliberation with contract checks, repair, and audits.
    """

    def __init__(self, synapse_client: SynapseClient, max_rounds: int = 3, deliberation_budget: int = 5) -> None:
        self.synapse = synapse_client
        self.max_rounds = max_rounds
        self.deliberation_budget = deliberation_budget

    async def deliberate(
        self,
        *,
        working_context: WorkingContext,
        episode_id: str,
        runlog: RunLogger | None = None,
        mode: str | None = None,
    ) -> DeliberationResult:
        call_id = uuid4().hex
        blackboard = {"hypotheses": {}, "remaining_budget": self.deliberation_budget}
        initial_plan_obj: dict[str, Any] = {}

        log.info(
            f"[Deliberation] ▶ Start | call_id={call_id} episode={episode_id} "
            f"goal='{_short(working_context.goal)}'"
        )

        # 0) HARDEN: ensure a concrete arm id exists and is registered
        await _ensure_strategy_arm(working_context, runlog=runlog)

        # 1) Generate hypotheses
        try:
            hypotheses_list = await self._invoke_hypothesis_generator(
                working_context, blackboard, runlog, call_id, episode_id,
            )
            for i, plan in enumerate(hypotheses_list[:3]):
                hyp_id = f"hyp_{chr(65 + i)}"
                blackboard["hypotheses"][hyp_id] = {"plan": plan, "audits": {}, "status": "active"}
            if not blackboard["hypotheses"]:
                return DeliberationResult(status="rejected", reason="Hypothesis Generator produced no plans.")
            initial_plan_obj = next(iter(blackboard["hypotheses"].values()))["plan"]
        except Exception as e:
            log.error(
                f"[Deliberation] ✖ Hypothesis generation crash | call_id={call_id} err={e!r}",
                exc_info=True,
            )
            return DeliberationResult(status="error", reason=f"Hypothesis generation failed: {e!r}")

        # 2) Audit loops with moderator control
        for round_num in range(self.max_rounds):
            log.info(
                f"[Deliberation] ▶ Round {round_num + 1}/{self.max_rounds} | "
                f"budget={blackboard['remaining_budget']}"
            )
            active_hyps = {k: v for k, v in blackboard["hypotheses"].items() if v["status"] == "active"}
            if not active_hyps:
                log.warning("[Deliberation] No active hypotheses remain. Terminating.")
                return DeliberationResult(
                    status="rejected", reason="All hypotheses were pruned.", initial_plan=initial_plan_obj,
                )

            # Fan-out soft auditors (best-effort)
            audit_tasks = [
                task
                for hyp_id, hyp in active_hyps.items()
                for task in self._dispatch_auditors(
                    hyp_id, hyp, working_context, blackboard, runlog, call_id, episode_id,
                )
            ]
            for result in await asyncio.gather(*audit_tasks, return_exceptions=True):
                if isinstance(result, tuple) and len(result) == 3:
                    hyp_id, auditor_name, audit_finding = result
                    if hyp_id in blackboard["hypotheses"]:
                        blackboard["hypotheses"][hyp_id]["audits"][auditor_name] = audit_finding

            # Moderator
            try:
                moderator_decision = await self._invoke_moderator(
                    working_context, blackboard, runlog, call_id, episode_id,
                )
            except Exception as e:
                log.error(
                    f"[Deliberation] ✖ Moderator crash | call_id={call_id} err={e!r}",
                    exc_info=True,
                )
                return DeliberationResult(status="error", reason=f"Moderator failed: {e!r}")

            action = (moderator_decision.get("action") or "terminate").lower()
            log.info(
                f"[Deliberation] Moderator Action: {action.upper()} | "
                f"Reason: {_short(moderator_decision.get('reasoning'))}"
            )

            if action == "approve":
                winner_id = moderator_decision.get("winning_hypothesis_id")
                if not winner_id or winner_id not in blackboard["hypotheses"]:
                    return DeliberationResult(
                        status="rejected",
                        reason="Moderator selected an unknown hypothesis.",
                        initial_plan=initial_plan_obj,
                    )

                candidate_plan = blackboard["hypotheses"][winner_id]["plan"]
                approved_dict = await self._enforce_contract_with_repair(candidate_plan, working_context)
                if not approved_dict:
                    return DeliberationResult(
                        status="rejected",
                        reason="Gatekeeper/auditors rejected the plan after repair attempt.",
                        initial_plan=initial_plan_obj,
                    )

                final_plan = self._finalize_for_execution(
                    approved_dict, working_context.strategy_arm, list(working_context.allowed_tools or []),
                )
                return DeliberationResult(
                    status="approved",
                    reason="Plan approved by gatekeeper and auditors.",
                    initial_plan=initial_plan_obj,
                    final_plan=final_plan,
                )

            elif action == "synthesize":
                try:
                    synthesized_plan = await self._invoke_synthesizer(
                        moderator_decision.get("synthesis_inputs", {}),
                        working_context,
                        blackboard,
                        runlog,
                        call_id,
                        episode_id,
                    )
                    if synthesized_plan:
                        # PROMOTE synthesizer strategy to arm (critical wiring fix)
                        await _promote_synth_strategy(working_context, synthesized_plan, runlog=runlog)
                        log.info("[Deliberation] Synthesized a new plan, attempting immediate validation.")
                        approved_dict = await self._enforce_contract_with_repair(synthesized_plan, working_context)

                        if approved_dict:
                            # If it's valid, finalize and return it immediately.
                            log.info("[Deliberation] ✓ Synthesized plan approved.")
                            final_plan = self._finalize_for_execution(
                                approved_dict, working_context.strategy_arm, list(working_context.allowed_tools or []),
                            )
                            return DeliberationResult(
                                status="approved",
                                reason="A new plan was synthesized and approved.",
                                initial_plan=initial_plan_obj,
                                final_plan=final_plan,
                            )
                        else:
                            # The new plan is invalid. Add it to the blackboard and let the loop continue.
                            log.warning("[Deliberation] Synthesized plan failed validation, will continue deliberation.")
                            new_hyp_id = f"hyp_{chr(65 + len(blackboard['hypotheses']))}"
                            blackboard["hypotheses"][new_hyp_id] = {
                                "plan": synthesized_plan,
                                "audits": {},
                                "status": "active",
                            }
                            continue
                        new_hyp_id = f"hyp_{chr(65 + len(blackboard['hypotheses']))}"
                        blackboard["hypotheses"][new_hyp_id] = {
                            "plan": synthesized_plan,
                            "audits": {},
                            "status": "active",
                        }
                        for p_id in moderator_decision.get("synthesis_inputs", {}).get("parent_hypotheses", []):
                            if p_id in blackboard["hypotheses"] and p_id != new_hyp_id:
                                blackboard["hypotheses"][p_id]["status"] = "deactivated"
                    continue
                except Exception as e:
                    log.error(
                        f"[Deliberation] ✖ Synthesizer crash | call_id={call_id} err={e!r}",
                        exc_info=True,
                    )
                    return DeliberationResult(status="error", reason=f"Synthesizer failed: {e!r}")

            elif action == "continue":
                # loop again (budget decreases in _invoke_moderator)
                continue

            # unknown / terminate
            return DeliberationResult(
                status="rejected",
                reason=moderator_decision.get("reasoning", "Moderator terminated."),
                initial_plan=initial_plan_obj,
            )

        # -------------------------- FINAL-ROUND CONVERGENCE --------------------------
        log.warning(
            f"[Deliberation] Max rounds ({self.max_rounds}) reached; converging on best hypothesis."
        )
        best_id = self._pick_best_hypothesis(blackboard["hypotheses"])
        if best_id:
            candidate_plan = blackboard["hypotheses"][best_id]["plan"]
            approved_dict = await self._enforce_contract_with_repair(candidate_plan, working_context)
            if approved_dict:
                final_plan = self._finalize_for_execution(
                    approved_dict, working_context.strategy_arm, list(working_context.allowed_tools or []),
                )
                return DeliberationResult(
                    status="approved",
                    reason="Auto-approved best hypothesis on final round.",
                    initial_plan=initial_plan_obj,
                    final_plan=final_plan,
                )

        return DeliberationResult(
            status="rejected",
            reason=f"Max deliberation rounds ({self.max_rounds}) reached with no viable plan.",
            initial_plan=initial_plan_obj,
        )

    # ------------------------------------------------------------------
    # Contract enforcement with one-shot repair + soft audits
    # ------------------------------------------------------------------
    async def _enforce_contract_with_repair(self, plan_like: dict, ctx: WorkingContext) -> dict | None:
        """Validate plan against PlanSpec + deterministic gatekeeper; attempt a single structured repair; run soft audits."""
        raw_dict = plan_like if isinstance(plan_like, dict) else {}

        capped = _cap_context(ctx)
        base_ok, base_reason, spec_or_none = _gatekeep_contract(
            raw_dict,
            strategy_arm_id=capped["strategy_arm_id"],
            allowed_tools=capped["allowed_tools"],
            write_scope_paths=capped["write_scope_paths"],
            forbidden_paths=capped["forbidden_paths"],
            required_verification_types=capped["required_verification_types"],
        )
        if not base_ok:
            # Attempt a single structured repair via LLM
            repair_prompt = {
                "role": "user",
                "content": (
                    "Repair this plan JSON to satisfy the following **general constraints**:\n"
                    f"- strategy_id MUST be exactly '{capped['strategy_arm_id']}'\n"
                    f"- Steps MUST use ONLY allowed tools: {capped['allowed_tools']}\n"
                    f"- Any write MUST be an 'apply_patch' with unified diff; touched files MUST be within "
                    f"{capped['write_scope_paths']} and MUST NOT touch {capped['forbidden_paths']}\n"
                    f"- verification_checks MUST include: {capped['required_verification_types']}\n"
                    "- Keep content concise and executable. Return ONLY JSON matching the PlanSpec."
                ),
            }
            rep = await call_llm_service_direct(
                prompt=repair_prompt,
                agent_name="Simula.Synthesizer",
                scope="simula.deliberation.synthesizer",
            )
            repaired = extract_json_flex(getattr(rep, "text", "")) or {}
            base_ok2, base_reason2, spec_or_none = _gatekeep_contract(
                repaired,
                strategy_arm_id=capped["strategy_arm_id"],
                allowed_tools=capped["allowed_tools"],
                write_scope_paths=capped["write_scope_paths"],
                forbidden_paths=capped["forbidden_paths"],
                required_verification_types=capped["required_verification_types"],
            )
            if not base_ok2:
                log.warning("[Deliberation] Gatekeeper rejection after repair: %s", base_reason2)
                return None
            raw_dict = repaired

        # Soft audits (non-blocking if they error, but blocking on explicit reject)
        ok_soft, reason_soft = await _audit_secondary_llm(raw_dict)
        if not ok_soft:
            log.warning("[Deliberation] Secondary audit rejection: %s", reason_soft)
            return None

        # Defensive final schema validation
        try:
            PlanSpec.model_validate(raw_dict)
        except ValidationError as e:
            log.error("[Deliberation] Contract invalid after audits: %s", e)
            return None
        return raw_dict

    # ------------------------------------------------------------------
    # LLM agent wrappers + utilities
    # ------------------------------------------------------------------
    async def _safe_build_prompt(self, *, scope: str, context: dict, summary: str) -> Any:
        """
        Build a prompt with guards against empty message sets. If the orchestrated
        prompt renders empty, create a minimal user message as a fallback.
        """
        try:
            pr = await build_prompt(scope=scope, context=context, summary=summary)
        except Exception as e:
            log.warning("[Deliberation] build_prompt failed for %s: %r", scope, e)
            pr = None

        # Insert meta guards directly in context to avoid 'unknown' propagation
        if "strategy_arm_id" not in context or _needs_fallback_arm(context.get("strategy_arm_id")):
            context = {**context, "strategy_arm_id": FALLBACK_ARM_ID}

        # If the prompt object exists but has no messages (or provider_overrides missing), create a minimal one
        def _messages_len(p) -> int:
            try:
                return len(getattr(p, "messages", []) or [])
            except Exception:
                return 0

        if pr and _messages_len(pr) > 0:
            return pr

        # Minimal fallback
        minimal = {
            "messages": [
                {
                    "role": "system",
                    "content": f"You are {scope}. Keep outputs compact; return ONLY JSON when asked.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "summary": summary or "",
                            "context": context,
                        }
                    ),
                },
            ],
            "provider_overrides": {"model": "gpt-4o-mini", "temperature": 0.2, "max_tokens": 1200},
        }
        return minimal

    def _dispatch_auditors(self, hyp_id: str, hypothesis: dict, *args) -> list[asyncio.Task]:
        """Creates asyncio tasks for all specialist auditors."""
        auditors = {
            "ImportAuditor": "Verify imports are correct and necessary.",
            "TypeHygieneAuditor": "Check for type consistency and obvious errors.",
            "GoalObedienceAuditor": "Ensure the plan strictly adheres to the user's goal.",
            "SecurityAuditor": "Scan for potential security/safety issues.",
            "RedTeamAuditor": "Critique for logical flaws or inefficiencies.",
        }
        return [
            asyncio.create_task(
                self._invoke_aspect_auditor(hyp_id, hypothesis, name, summary, *args),
            )
            for name, summary in auditors.items()
        ]

    async def _invoke_llm_agent(
        self,
        scope: str,
        agent_name: str,
        context: dict,
        summary: str,
        runlog: RunLogger | None,
        episode_id: str,
        timeout: float,
    ) -> dict:
        """Generic LLM invocation wrapper with feedback logging to Synapse, and guards against empty prompts."""
        prompt_response = await self._safe_build_prompt(scope=scope, context=context, summary=summary)

        # Ensure provenance
        try:
            prompt_response.provenance = {"synapse_episode_id": episode_id}  # if RenderedPrompt
        except Exception:
            # plain dict fallback
            pass

        llm_response = await call_llm_service_direct(
            prompt_response, agent_name=agent_name, scope=scope, timeout=timeout,
        )
        text = getattr(llm_response, "text", "") or ""
        if runlog:
            runlog.log_llm(
                phase=scope.split(".")[-1],
                scope=scope,
                agent=agent_name,
                completion_text=text,
            )

        parsed_json = (
            llm_response.json
            if isinstance(llm_response.json, dict)
            else (extract_json_flex(text) or {})
        )

        # Feedback loop to Synapse (best-effort)
        try:
            metrics = {"success": 1.0 if parsed_json else 0.0}
            if isinstance(parsed_json, dict):
                if "approved" in parsed_json:
                    metrics["approved"] = 1.0 if parsed_json["approved"] else 0.0
                if "action" in parsed_json:
                    metrics["action"] = parsed_json["action"]
                arm_hint = context.get("strategy_arm_id") or context.get("selected_arm_id")
                if arm_hint:
                    metrics["chosen_arm_id"] = arm_hint
            asyncio.create_task(
                self.synapse.log_outcome(
                    episode_id=episode_id,
                    task_key=scope,
                    metrics=metrics,
                ),
            )
        except Exception as e:
            log.warning(f"[Deliberation] Failed to log outcome to Synapse for {scope}: {e!r}")

        return parsed_json

    async def _invoke_hypothesis_generator(
        self,
        context: WorkingContext,
        blackboard: dict,
        runlog: RunLogger | None,
        call_id: str,
        episode_id: str,
    ) -> list[dict]:
        # Tight, compact, contract-driven request to avoid long outputs and truncation
        capped = _cap_context(context)
        prompt = await self._safe_build_prompt(
            scope="simula.deliberation.hypothesis_generator",
            context={**capped, "output_contract": "scl_hypothesis_generator_output_contract"},
            summary="Return ONLY compact JSON per contract. Keep plans ≤4 steps each.",
        )
        # Provide defaults if provider_overrides missing
        try:
            po = getattr(prompt, "provider_overrides", None)
            if isinstance(po, dict):
                po.update({"model": "gpt-4o-mini", "temperature": 0.2, "max_tokens": 1600})
            elif isinstance(prompt, dict):
                prompt.setdefault("provider_overrides", {"model": "gpt-4o-mini", "temperature": 0.2, "max_tokens": 1600})
        except Exception:
            pass

        res = await call_llm_service_direct(
            prompt, agent_name="Simula.HypothesisGenerator", scope="simula.deliberation.hypothesis_generator",
        )
        text = getattr(res, "text", "") or ""
        obj = res.json if isinstance(res.json, dict) else (extract_json_flex(text) or {})

        if not obj and ("{" in text and "]" in text):
            salvaged = _salvage_json(text)
            if salvaged:
                obj = salvaged

        hyps = obj.get("hypotheses", []) if isinstance(obj, dict) else []
        return hyps

    async def _invoke_aspect_auditor(
        self,
        hyp_id: str,
        hypothesis: dict,
        name: str,
        summary: str,
        context: WorkingContext,
        blackboard: dict,
        runlog: RunLogger | None,
        call_id: str,
        episode_id: str,
    ) -> tuple[str, str, dict]:
        capped = _cap_context(context)
        prompt_context = {
            "goal": context.goal,
            "target_fqname": context.target_fqname,
            "strategy_arm_id": capped["strategy_arm_id"],
            "hypothesis_to_audit": hypothesis["plan"],
            "agent_name": f"Simula.{name}",
        }

        finding = await self._invoke_llm_agent(
            "simula.deliberation.auditor",
            f"Simula.{name}",
            prompt_context,
            f"Focus: {summary}",
            runlog,
            episode_id,
            45.0,
        )

        # Meta-guard: if auditor responds with empty or with "unknown strategy" style rejections,
        # mark the finding but don't let it perma-stall future rounds.
        if not finding:
            finding = {"approved": False, "reason": "empty_auditor_response"}
        return hyp_id, name, finding

    async def _invoke_synthesizer(
        self,
        inputs: dict,
        context: WorkingContext,
        blackboard: dict,
        runlog: RunLogger | None,
        call_id: str,
        episode_id: str,
    ) -> dict | None:
        prompt_context = _cap_context(context)
        prompt_context.update({"blackboard": blackboard, **inputs})
        result = await self._invoke_llm_agent(
            "simula.deliberation.synthesizer",
            "Simula.Synthesizer",
            prompt_context,
            "",
            runlog,
            episode_id,
            90.0,
        )
        return result or None

    async def _invoke_moderator(
        self,
        context: WorkingContext,
        blackboard: dict,
        runlog: RunLogger | None,
        call_id: str,
        episode_id: str,
    ) -> dict:
        capped = _cap_context(context)
        prompt_context = {"goal": context.goal, "blackboard": blackboard, "strategy_arm_id": capped["strategy_arm_id"]}
        blackboard["remaining_budget"] -= 1
        decision = await self._invoke_llm_agent(
            "simula.deliberation.moderator",
            "Simula.Moderator",
            prompt_context,
            "",
            runlog,
            episode_id,
            60.0,
        )
        # Meta-fix: if moderator is empty, gracefully continue once
        return decision or {"action": "continue", "reasoning": "empty_moderator_response"}

    # ------------------------------------------------------------------
    # Finalization for execution (preserves PlanSpec steps)
    # ------------------------------------------------------------------
    def _finalize_for_execution(
        self,
        audited_plan_spec: dict,
        champion_arm: ArmScore,
        allowed_tools: list[str],
    ) -> dict[str, Any]:
        """
        Accepts a JSON object that conforms to PlanSpec and returns the
        normalized payload expected by the SCL orchestrator.
        """
        plan_spec = PlanSpec.model_validate(audited_plan_spec)

        normalized = {
            "strategy_id": plan_spec.strategy_id,
            "strategy_rationale": plan_spec.strategy_rationale,
            "plan": [s.model_dump() for s in plan_spec.plan],
            "verification_checks": [v.model_dump() for v in plan_spec.verification_checks],
            "allowed_tools": list(allowed_tools or []),
            "invariants": {"must": [], "forbid": []},
            "budget": {"max_steps": 12},
        }

        base_arm_id = _safe_arm_id(champion_arm)
        dyn_arm_id = f"dyn::{_sha16_for({'base_arm': base_arm_id, 'plan': normalized})}"
        normalized.update({"champion_arm_id": base_arm_id, "dynamic_plan_arm_id": dyn_arm_id})

        log.info(
            "[Deliberation] ✓ Plan Finalized | dynamic_arm=%s steps=%d",
            dyn_arm_id,
            len(normalized["plan"]),
        )
        asyncio.create_task(register_dynamic_arm_in_graph(dyn_arm_id, "simula_planful"))
        return normalized

    # ------------------------------------------------------------------
    # Heuristics
    # ------------------------------------------------------------------
    def _pick_best_hypothesis(self, hyps: dict) -> str | None:
        """
        Choose a hypothesis by a simple score: +1 per approving auditor, -1 per rejecting.
        If no audits, prefer the first active (stable behavior).
        """
        best_id, best_score = None, float("-inf")
        for hid, item in hyps.items():
            if item.get("status") != "active":
                continue
            audits = item.get("audits", {}) or {}
            score = 0
            for finding in audits.values():
                approved = False
                if isinstance(finding, dict):
                    approved = bool(finding.get("approved"))
                score += 1 if approved else -1
            if audits and score > best_score:
                best_id, best_score = hid, score

        if best_id is not None:
            return best_id

        # fallback: first active
        for hid, item in hyps.items():
            if item.get("status") == "active":
                return hid
        return None
