# systems/voxis/core/pipeline.py
# --- DEFINITIVE VERSION - COLLABORATIVE POLICY + LLM ARCHITECTURE (HARDENED) ---

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx  # HTTP client for TTS

from api.endpoints.synapse.planning import select_or_plan as _select_or_plan

# --- Core System & Canonical Service Clients ---
from core.llm.bus import event_bus
from core.prompting.lenses import lens_tools_catalog
from core.prompting.orchestrator import build_prompt, run_voxis_synthesis
from core.services.synapse import synapse
from core.utils.llm_gateway_client import (
    call_llm_service,
    call_llm_service_direct,
    extract_json_flex,
)
from core.utils.neo.cypher_query import cypher_query
from systems.axon.dependencies import get_driver_registry
from systems.synapse.schemas import (
    ArmScore,
    Candidate,
    SelectArmResponse,
)
from systems.synapse.schemas import SelectArmRequest as _SelectArmRequest
from systems.synapse.schemas import (
    TaskContext as SynapseTaskContext,
)
from systems.synapse.schemas import TaskContext as _TaskContext

# --- Local Module Imports ---
from systems.voxis.core.models import EosPlan, VoxisTalkRequest
from systems.voxis.core.result_store import AbstractResultStore
from systems.voxis.core.user_profile import (
    build_context_for_voxis,
    ensure_soul_profile,
    ingest_turn_node,
    link_input_to_response,
    normalize_profile_upsert_from_llm,
    upsert_soul_profile_properties,
)

logger = logging.getLogger(__name__)

# ----------- CONFIG / CONSTANTS -----------
MAX_PLANS = 2
IT_BAD_PREFIXES = ("hey", "hi", "hello", "thanks for your patience", "hang tight", "got it", "okay")
IT_BAD_EMOJI_CHARS = set(
    "🙂😀😁😂🤣😊😍🥰😘😎😉😄😅🙃🤗🤔🙏👍👌✨⭐️🎉🔥💪😌😇🙌😭🥳😜😏😉😴😬😑😤😮😃😆"
)
TTS_ENDPOINT_URL = "http://127.0.0.1:8000/voxis/tts/synthesize"  # TTS endpoint

# ----------- tiny helpers (kept lean to avoid perf regressions) -----------


def _format_memory_block(memory: dict[str, Any]) -> str:
    lines: list[str] = []
    profile = memory.get("soul_profile") or {}
    if profile:
        lines.append(f"Name: {profile.get('name') or '—'}")
    prefs = (memory.get("preferences") or {}) if isinstance(memory.get("preferences"), dict) else {}
    if prefs:
        lines.append(f"Prefs: {', '.join(sorted(prefs.keys()))}")
    return "\n".join(lines).strip() or "No memories available."


async def _maybe_await(x):
    if hasattr(x, "__await__"):
        return await x
    return x


def _sanitize_tool_params(tool_name: str | None, params: dict[str, Any]) -> dict[str, Any]:
    """Drop unknown params that some LLMs hallucinate; keeps drivers stable."""
    if not tool_name or "." not in tool_name or not isinstance(params, dict):
        return params
    driver, endpoint = tool_name.split(".", 1)
    allow: set[str] | None = None
    if driver == "open_meteo" and endpoint == "probe":
        allow = {"location", "forecast_days", "hourly", "daily", "current"}
    if allow is None:
        return params
    return {k: v for k, v in params.items() if k in allow}


def _clip(s: str | None, limit: int = 4000) -> str:
    if not s:
        return ""
    if len(s) <= limit:
        return s
    return s[:limit]


def _normalize_interim_thought(s: str) -> str:
    s = (s or "").strip()
    low = s.lower()
    # strip greetings / filler
    if any(low.startswith(p) for p in IT_BAD_PREFIXES):
        s = ""
    # strip emojis
    s = "".join(ch for ch in s if ch not in IT_BAD_EMOJI_CHARS)
    # default if empty
    if not s:
        s = "Reviewing the latest message and shaping the response…"
    # enforce ellipsis
    if not s.endswith("…"):
        s = s.rstrip(". ") + "…"
    return s


def _plan_from_arm_content(arm: ArmScore) -> dict | None:
    """If select_or_plan already produced a full plan, use it — avoid double planning."""
    content = getattr(arm, "content", None)
    if not isinstance(content, dict):
        return None
    has_min = (
        isinstance(content.get("plan"), list)
        and ("final_synthesis_prompt" in content)
        and ("interim_thought" in content or "scratchpad" in content)
    )
    return content if has_min else None


def _coerce_plan_steps(raw_plan) -> list[dict]:
    """Ensure each step is shaped correctly for EosPlan: dicts, valid action, dict params."""
    steps: list[dict] = []
    if not isinstance(raw_plan, list):
        return [{"action_type": "respond", "tool_name": None, "parameters": {}}]

    for s in raw_plan:
        if not isinstance(s, dict):
            continue
        action = str(s.get("action_type") or "").lower()
        if action not in ("tool_call", "respond"):
            action = "respond"
        tool_name = s.get("tool_name") if action == "tool_call" else None
        params = s.get("parameters")
        if not isinstance(params, dict):
            params = {}
        steps.append({"action_type": action, "tool_name": tool_name, "parameters": params})

    if not any(step.get("action_type") == "respond" for step in steps):
        steps.append({"action_type": "respond", "tool_name": None, "parameters": {}})
    return steps


# --- TTS CLIENT FUNCTION ---
async def _trigger_synthesis_job(
    main_text: str,
    interim_text: str,
    voice_name: str | None = None,
) -> dict[str, Any]:
    """Calls the TTS service and returns the parsed response."""
    payload = {"text": main_text, "interim_text_override": interim_text}
    if voice_name:
        payload["voice_name"] = voice_name

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(TTS_ENDPOINT_URL, json=payload)
            response.raise_for_status()
            return {
                "interim_audio_b64": base64.b64encode(response.content).decode("utf-8"),
                "full_audio_job_id": response.headers.get("x-job-id"),
                "full_audio_poll_url": response.headers.get("x-poll-url"),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"TTS service error: {e.response.status_code} - {e.response.text}")
            return {"error": f"TTS service failed: {e.response.text}"}
        except Exception as e:
            logger.error(f"TTS service connection failed: {e}", exc_info=True)
            return {"error": "Failed to connect to the TTS service."}


class VoxisPipeline:
    def __init__(self, req: VoxisTalkRequest, result_store: AbstractResultStore, decision_id: str):
        self.request = req
        self.result_store = result_store
        self.decision_id = decision_id
        self.log_extra = {
            "user_id": req.user_id,
            "session_id": req.session_id,
            "decision_id": decision_id,
        }
        self._telem_sent: bool = False
        self._planned_count: int = 0  # cap re-plans at MAX_PLANS

    # ----------------- INTERNAL: scorer feedback logger -----------------
    async def _log_scorer_feedback(
        self,
        *,
        arm_id: str,
        utility_score: float,
        reasoning: str,
        context: dict[str, Any],
    ) -> None:
        """
        Persist UtilityScorer feedback to Neo4j using cypher_query.
        Compatible with existing PolicyArm nodes (id is the arm_id).
        """
        # Defensive sanitization
        try:
            score = float(utility_score)
        except Exception:
            score = 0.0
        score = max(0.0, min(1.0, score))

        feedback_id = str(uuid.uuid4())

        # Pull optional context fields safely
        user_input = _clip(context.get("user_input"))
        final_response = _clip(context.get("final_agent_response"))
        critic_summary = _clip(context.get("critic_summary"))
        episode_id = _clip(context.get("episode_id"))
        task_key = _clip(context.get("task_key"))
        # If you capture sufficiency/critic verdicts elsewhere, pass them in context:
        is_sufficient = bool(context.get("is_sufficient")) if "is_sufficient" in context else None

        query = """
        // Ensure the arm node exists (PolicyArm matches your registry schema)
        MERGE (a:PolicyArm {id: $arm_id})

        // Create an immutable feedback event node
        CREATE (f:ScorerFeedback {
          id: $id,
          utility_score: $utility_score,
          reasoning: $reasoning,
          user_input: $user_input,
          final_response: $final_response,
          critic_summary: $critic_summary,
          episode_id: $episode_id,
          task_key: $task_key,
          is_sufficient: $is_sufficient,
          created_at: datetime()
        })

        MERGE (a)-[:HAS_FEEDBACK]->(f)
        """

        params = {
            "id": feedback_id,
            "arm_id": arm_id,
            "utility_score": score,
            "reasoning": _clip(reasoning),
            "user_input": user_input,
            "final_response": final_response,
            "critic_summary": critic_summary,
            "episode_id": episode_id,
            "task_key": task_key,
            "is_sufficient": is_sufficient,
        }

        await cypher_query(query, params)

    # ------------- PLANNING --------------

    async def _run_unified_llm_planner(
        self, task_ctx: SynapseTaskContext, champion_arm: ArmScore
    ) -> EosPlan:
        logger.info(
            f"[Pipeline] Running unified planner, guided by arm '{champion_arm.arm_id}'.",
            extra={**self.log_extra, "planned_count": self._planned_count},
        )

        # Conversational/no-tools arms → respond-only plan
        is_conversational_arm = (
            "no_tools" in champion_arm.arm_id or "conversational" in champion_arm.arm_id
        )
        if is_conversational_arm:
            return EosPlan(
                episode_id=(task_ctx.metadata or {}).get("episode_id", "fallback-episode"),
                champion_arm_id=champion_arm.arm_id,
                interim_thought=_normalize_interim_thought(
                    "Drafting a direct reply based on your last message…"
                ),
                scratchpad="Conversational arm selected; skipping tool usage.",
                plan=[{"action_type": "respond", "tool_name": None, "parameters": {}}],
                final_synthesis_prompt=(
                    f"The user said '{self.request.user_input}'. Reply directly and helpfully; do not use tools."
                ),
                profile_upserts=[],
            )

        # Guided LLM planning
        planner_context = {"context": task_ctx.model_dump()}
        if task_ctx.metadata:
            planner_context.update(task_ctx.metadata)
        planner_context["goal"] = task_ctx.goal
        planner_context["episode_id"] = (task_ctx.metadata or {}).get(
            "episode_id", "unknown-episode"
        )
        planner_context["selected_policy_hints"] = champion_arm.policy_graph_meta or {}
        planner_context["selected_arm_id"] = champion_arm.arm_id

        try:
            prompt_response = await build_prompt(
                scope="voxis.main.planning",
                context=planner_context,
                summary="Plan a response, guided by policy hints.",
            )
            llm_response = await call_llm_service(
                prompt_response,
                agent_name="Voxis.Planner",
                scope="voxis.main.planning",
            )
            plan_json = extract_json_flex(
                getattr(llm_response, "text", "") or getattr(llm_response, "content", "")
            )
            if not isinstance(plan_json, dict):
                raise ValueError("LLM Planner did not return a valid JSON object.")

            # normalize fields
            plan_json["champion_arm_id"] = champion_arm.arm_id
            plan_json["interim_thought"] = _normalize_interim_thought(
                plan_json.get("interim_thought")
                if isinstance(plan_json.get("interim_thought"), str)
                else "",
            )
            if not isinstance(plan_json.get("scratchpad"), str):
                plan_json["scratchpad"] = ""

            # coerce plan steps
            plan_json["plan"] = _coerce_plan_steps(plan_json.get("plan"))
            return EosPlan.model_validate(plan_json)
        except TimeoutError:
            logger.warning(
                "[Pipeline] Planner timed out; using minimal fallback.", extra=self.log_extra
            )
        except Exception as e:
            logger.error(
                f"[Pipeline] Unified LLM Planner FAILED: {e}", exc_info=True, extra=self.log_extra
            )

        # minimal fallback
        return EosPlan(
            episode_id=(task_ctx.metadata or {}).get("episode_id", "fallback-episode"),
            champion_arm_id="dyn::minimal_fallback",
            interim_thought=_normalize_interim_thought("Providing a minimal direct reply…"),
            scratchpad="Planner fallback: internal error or timeout.",
            plan=[{"action_type": "respond", "tool_name": None, "parameters": {}}],
            final_synthesis_prompt=f"Provide a concise, helpful reply. User's last message: {self.request.user_input}",
            profile_upserts=[],
        )

    async def run_planning_phase(
        self,
        failure_context: str | None = None,
    ) -> tuple[EosPlan, SynapseTaskContext, SelectArmResponse | None]:
        # Respect the hard cap
        if self._planned_count >= MAX_PLANS:
            logger.info("[Pipeline] Planning cap reached; reusing last plan.", extra=self.log_extra)
            raise RuntimeError("Planning cap reached.")

        memory_ctx = await build_context_for_voxis(
            user_id=self.request.user_id,
            session_id=self.request.session_id,
            user_input=self.request.user_input,
        )
        memory_block = _format_memory_block(memory_ctx)

        tool_catalog_result = await lens_tools_catalog({})
        candidates = [
            Candidate(id=tool["function"]["name"], content=tool)
            for tool in tool_catalog_result.get("tools_catalog", {}).get("candidates", [])
        ]
        candidates.append(
            Candidate(
                id="conversational_response",
                content={
                    "function": {
                        "name": "conversational_response",
                        "description": "Engage without tools.",
                    }
                },
            ),
        )

        task_ctx = SynapseTaskContext(
            task_key="voxis_conversational_turn",
            goal=f"Respond helpfully to user input: '{self.request.user_input}'",
            metadata={
                "user_id": self.request.user_id,
                "session_id": self.request.session_id,
                "user_input": self.request.user_input,
                "memory": memory_ctx,
                "memory_context_str": memory_block,
                "failure_context": failure_context,
                "planned_count": self._planned_count,
                "planner_hints": {"max_plans": MAX_PLANS},
            },
        )

        try:
            selection = await synapse.select_or_plan(task_ctx, candidates)
            self.log_extra["episode_id"] = selection.episode_id
            task_ctx.metadata["episode_id"] = selection.episode_id
            champion = selection.champion_arm
        except (TimeoutError, Exception) as e:
            logger.warning(
                f"[Pipeline] select_or_plan failed ({e}); using fallback arm.", extra=self.log_extra
            )
            selection = None

            # lightweight struct for arm_id/score/reason compatibility
            class _Arm:
                def __init__(self, arm_id, score, reason, policy_graph_meta):
                    self.arm_id = arm_id
                    self.score = score
                    self.reason = reason
                    self.policy_graph_meta = policy_graph_meta

            champion = _Arm("fallback", 0.0, str(e), {})

        # If Synapse already produced a plan, use it directly
        direct_plan_dict = _plan_from_arm_content(champion)
        if isinstance(direct_plan_dict, dict):
            # normalize & validate
            direct_plan_dict["interim_thought"] = _normalize_interim_thought(
                direct_plan_dict.get("interim_thought")
                if isinstance(direct_plan_dict.get("interim_thought"), str)
                else "",
            )
            if not isinstance(direct_plan_dict.get("scratchpad"), str):
                direct_plan_dict["scratchpad"] = ""
            # coerce steps
            direct_plan_dict["plan"] = _coerce_plan_steps(direct_plan_dict.get("plan"))
            direct_plan_dict.setdefault(
                "episode_id", getattr(selection, "episode_id", None) or "fallback-episode"
            )
            direct_plan_dict.setdefault("champion_arm_id", getattr(champion, "arm_id", "fallback"))
            plan = EosPlan.model_validate(direct_plan_dict)
        else:
            plan = await self._run_unified_llm_planner(task_ctx, champion)

        # surface interim_thought fast
        if plan.interim_thought:
            await self.result_store.update_field(
                self.decision_id, "interim_thought", plan.interim_thought
            )

        # increment planner count here (successful plan produced)
        self._planned_count += 1
        return plan, task_ctx, selection

    # ------------- EXECUTION --------------

    async def _execute_plan(self, plan_steps: list[Any]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        reg = get_driver_registry()
        i = 0
        while i < len(plan_steps or []):
            step = plan_steps[i]
            action_type = getattr(step, "action_type", None) or (
                isinstance(step, dict) and step.get("action_type")
            )

            if action_type != "tool_call":
                if action_type == "respond":
                    results[f"step_{i}_respond"] = {"status": "queued_for_synthesis"}
                i += 1
                continue

            tool_tasks = []
            while i < len(plan_steps):
                tool_step = plan_steps[i]
                action_type_inner = getattr(tool_step, "action_type", None) or (
                    isinstance(tool_step, dict) and tool_step.get("action_type")
                )
                if action_type_inner != "tool_call":
                    break

                tool_name = getattr(tool_step, "tool_name", None) or (
                    isinstance(tool_step, dict) and tool_step.get("tool_name")
                )
                params = (
                    getattr(tool_step, "parameters", None)
                    if not isinstance(tool_step, dict)
                    else tool_step.get(
                        "parameters",
                    )
                )
                params = _sanitize_tool_params(tool_name, params or {})
                params["user_id"] = self.request.user_id

                async def run_tool(name, p, idx):
                    try:
                        driver_name, endpoint = (name or "").split(".", 1)
                        driver = reg.get(driver_name)
                        if not driver or not hasattr(driver, endpoint):
                            return idx, {"error": f"Tool '{name}' not found."}
                        return idx, await getattr(driver, endpoint)(p)
                    except Exception as e:
                        return idx, {"error": str(e)}

                tool_tasks.append(run_tool(tool_name, params, i))
                i += 1

            task_results = await asyncio.gather(*tool_tasks)
            for original_index, result_data in task_results:
                step_info = plan_steps[original_index]
                tool_name = getattr(step_info, "tool_name", None) or (
                    isinstance(step_info, dict) and step_info.get("tool_name")
                )
                results[f"step_{original_index}_{tool_name}"] = result_data
        return results

    # ------------- CRITICS --------------

    async def _run_fact_critic(
        self, plan: EosPlan, execution_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Critiques the execution results for factual sufficiency to answer the user's request."""
        logger.info(
            "[Pipeline] Starting Fact Critic step.",
            extra={**self.log_extra, "planned_count": self._planned_count},
        )

        try:
            has_tool_calls = any(
                (getattr(s, "action_type", None) or (isinstance(s, dict) and s.get("action_type")))
                == "tool_call"
                for s in (plan.plan or [])
            )
        except Exception:
            has_tool_calls = False

        if not has_tool_calls:
            return {
                "is_sufficient": True,
                "summary_of_facts": "Respond-only plan; no external facts required.",
            }

        critic_context = {
            "original_user_input": self.request.user_input,
            "final_synthesis_prompt": plan.final_synthesis_prompt,
            "interim_thought": plan.interim_thought,
            "plan": plan.model_dump(),
            "tool_execution_results": execution_results,
            "now_utc": datetime.now(UTC).isoformat(),
        }
        try:
            scope = "voxis.fact_critic.v1"
            prompt_response = await build_prompt(
                scope=scope,
                context=critic_context,
                summary="Critique plan execution results for factual sufficiency.",
            )
            llm_response = await call_llm_service_direct(
                prompt_response,
                agent_name="Voxis.FactCritic",
                scope=scope,
            )

            data: dict[str, Any] | None = None
            if hasattr(llm_response, "json") and callable(getattr(llm_response, "json", None)):
                try:
                    maybe = llm_response.json()
                    if isinstance(maybe, dict):
                        data = maybe
                except Exception:
                    data = None

            if data is None:
                text = getattr(llm_response, "text", "") or getattr(llm_response, "content", "")
                parsed = extract_json_flex(text)
                if isinstance(parsed, dict):
                    data = parsed

            if not isinstance(data, dict):
                raise ValueError("Fact Critic did not return a valid JSON object.")

            is_sufficient = bool(data.get("is_sufficient"))
            summary = data.get("summary_of_facts")
            if summary is None:
                summary = "" if is_sufficient else "Fact Critic returned no summary."

            return {"is_sufficient": is_sufficient, "summary_of_facts": summary}

        except TimeoutError:
            logger.warning("[Pipeline] Fact Critic timed out.", extra=self.log_extra)
            return {"is_sufficient": False, "summary_of_facts": "Fact Critic timed out."}
        except Exception as e:
            logger.error(
                f"[Pipeline] Fact Critic step FAILED: {e}", exc_info=True, extra=self.log_extra
            )
            return {
                "is_sufficient": False,
                "summary_of_facts": "An internal error occurred while verifying facts.",
            }

    async def _run_utility_scorer(
        self,
        final_response: str,
        execution_results: dict[str, Any],
        fact_critic_verdict: dict[str, Any],
        plan: EosPlan,
    ) -> dict[str, Any]:
        """Scores the overall utility of the final generated response (always emits a score)."""
        logger.info("[Pipeline] Starting Utility Scorer (post-turn).", extra=self.log_extra)
        try:
            scoring_context = {
                "user_input": self.request.user_input,
                "final_agent_response": final_response,
                "critic_summary": fact_critic_verdict.get("summary_of_facts"),
                "tool_results": execution_results,
                "plan": plan.model_dump(),
                "interim_thought": plan.interim_thought,
                "timestamp_utc": datetime.now(UTC).isoformat(),
            }

            # 1) Ask Synapse for a generic/base arm (NO planner)
            task_ctx = _TaskContext(
                task_key="voxis_utility_scorer",
                goal="Score the overall utility of the agent's turn.",
                risk_level="low",
                budget="constrained",
                metadata={
                    "user_id": getattr(self.request, "user_id", None),
                    "session_id": getattr(self.request, "session_id", None),
                },
            )
            sel = await _select_or_plan(_SelectArmRequest(task_ctx=task_ctx, candidates=[]))
            chosen_arm_id = sel.champion_arm.arm_id

            # 2) Build prompt and force provider to use the selected base arm
            prompt_response = await build_prompt(
                scope="voxis.utility_scorer",
                context=scoring_context,
                summary="Score the overall utility of the agent's turn.",
            )
            llm_response = await call_llm_service(
                prompt_response,
                agent_name="Voxis.UtilityScorer",
                scope="voxis.utility_scorer",
                provider_overrides={"arm_id": chosen_arm_id},
            )

            data: dict[str, Any] | None = None
            if hasattr(llm_response, "json") and callable(getattr(llm_response, "json", None)):
                try:
                    maybe = llm_response.json()
                    if isinstance(maybe, dict):
                        data = maybe
                except Exception:
                    data = None
            if data is None:
                text = getattr(llm_response, "text", "") or getattr(llm_response, "content", "")
                data = extract_json_flex(text)

            if isinstance(data, dict) and "utility_score" in data:
                logger.info(
                    f"[Pipeline] Utility score received: {data.get('utility_score')}",
                    extra=self.log_extra,
                )

                # --- OPTIONAL: Log to Neo4j for feedback-based generation ---
                await self._log_scorer_feedback(
                    arm_id=chosen_arm_id,
                    utility_score=data.get("utility_score"),
                    reasoning=data.get("reasoning"),
                    context=scoring_context,
                )

                return data

            return {"utility_score": 0.5, "reasoning": "Utility Scorer returned invalid format."}
        except Exception as e:
            logger.error(
                f"[Pipeline] Utility Scorer FAILED: {e}", exc_info=True, extra=self.log_extra
            )
            return {"utility_score": 0.5, "reasoning": f"Utility Scorer failed with exception: {e}"}

    # ------------- OUTCOME LOGGING --------------

    async def _run_and_log_outcome(
        self,
        episode_id: str,
        task_key: str,
        chosen_arm_id: str,
        expressive_text: str,
        execution_results: dict[str, Any],
        fact_critic_verdict: dict[str, Any],
        plan: EosPlan,
    ):
        utility_metrics = await self._run_utility_scorer(
            expressive_text, execution_results, fact_critic_verdict, plan
        )
        final_metrics = {
            "chosen_arm_id": chosen_arm_id,
            "success": 1.0 if fact_critic_verdict.get("is_sufficient") else 0.0,
            "idempotency_key": f"{episode_id}:{task_key}",
            **utility_metrics,
        }
        await synapse.log_outcome(episode_id=episode_id, task_key=task_key, metrics=final_metrics)

    async def _post_turn_telem(
        self,
        *,
        episode_id: str,
        task_key: str,
        chosen_arm_id: str,
        expressive_text: str,
        execution_results: dict[str, Any],
        fact_critic_verdict: dict[str, Any],
        plan: EosPlan,
        max_attempts: int = 5,
    ):
        if self._telem_sent:
            return
        self._telem_sent = True
        for attempt in range(max_attempts):
            try:
                await self._run_and_log_outcome(
                    episode_id,
                    task_key,
                    chosen_arm_id,
                    expressive_text,
                    execution_results,
                    fact_critic_verdict,
                    plan,
                )
                logger.info(
                    "[Pipeline] Logged comprehensive outcome to Synapse.", extra=self.log_extra
                )
                return
            except Exception as e:
                logger.error(
                    f"[Pipeline] Outcome logging failed (attempt {attempt + 1}/{max_attempts}): {e}",
                    extra=self.log_extra,
                )
                await asyncio.sleep((0.2 * (attempt + 1)) + random.uniform(0, 0.15))

    # ------------- PUBLIC ENTRYPOINTS --------------

    async def run_execution_phase(
        self,
        plan_and_context: tuple[EosPlan, SynapseTaskContext, SelectArmResponse | None],
    ) -> dict[str, Any]:
        final_plan, task_ctx, selection = plan_and_context
        memory_ctx = task_ctx.metadata.get("memory", {})
        memory_block = task_ctx.metadata.get("memory_context_str", "")

        # ingest user turn
        last_input_node_id = await ingest_turn_node(
            role="user",
            user_id=self.request.user_id or "user_anon",
            session_id=self.request.session_id or "unknown",
            text=self.request.user_input or "",
        )
        allow_profile_writes = bool(
            self.request.user_id and self.request.user_id not in ("user_anon", "unknown")
        )
        if allow_profile_writes:
            await ensure_soul_profile(self.request.user_id)

        # execute tools (if any)
        execution_results = await self._execute_plan(final_plan.plan)

        # fact critic
        critic_verdict = await self._run_fact_critic(final_plan, execution_results)
        if not isinstance(critic_verdict, dict):
            logger.warning(
                "[Pipeline] Fact Critic returned non-dict; coercing to failure.",
                extra=self.log_extra,
            )
            critic_verdict = {
                "is_sufficient": False,
                "summary_of_facts": "Fact Critic returned invalid format.",
            }

        # optional replan (bounded by MAX_PLANS)
        if not critic_verdict.get("is_sufficient") and self._planned_count < MAX_PLANS:
            failure_summary = critic_verdict.get(
                "summary_of_facts", "Fact Critic deemed results insufficient."
            )
            logger.warning(
                f"[Pipeline] Attempt {self._planned_count} INSUFFICIENT: {failure_summary}. Re-planning.",
                extra=self.log_extra,
            )
            replanned_tuple = await self.run_planning_phase(failure_context=failure_summary)
            final_plan, task_ctx, selection = replanned_tuple
            execution_results = await self._execute_plan(final_plan.plan)
            critic_verdict = await self._run_fact_critic(final_plan, execution_results)
            if critic_verdict.get("is_sufficient"):
                logger.info("[Pipeline] Re-plan SUCCEEDED.", extra=self.log_extra)
            else:
                logger.error(
                    "[Pipeline] Re-plan also FAILED critique. Proceeding with last attempt.",
                    extra=self.log_extra,
                )
        elif not critic_verdict.get("is_sufficient"):
            logger.error(
                "[Pipeline] Insufficient but planning cap reached — proceeding with last plan.",
                extra=self.log_extra,
            )
        else:
            logger.info("[Pipeline] Attempt 1 SUFFICIENT.", extra=self.log_extra)

        # optional profile upserts
        if final_plan and final_plan.profile_upserts and allow_profile_writes:
            try:
                merged_updates = normalize_profile_upsert_from_llm(
                    final_plan.model_dump(), user_id=self.request.user_id
                )
                if merged_updates:
                    await upsert_soul_profile_properties(
                        user_id=self.request.user_id,
                        properties=merged_updates,
                        source="planner",
                    )
                    logger.info("[Pipeline] Profile upsert applied.", extra=self.log_extra)
            except Exception as e:
                logger.warning(
                    f"[Pipeline] Profile upsert handling failed: {e}", extra=self.log_extra
                )

        # pick ids
        episode_id = (
            getattr(selection, "episode_id", None) or final_plan.episode_id or "fallback-episode"
        )
        chosen_arm_id = (
            (getattr(selection, "champion_arm", None) and selection.champion_arm.arm_id)
            or final_plan.champion_arm_id
            or "dyn::minimal_fallback"
        )

        # synthesis
        synthesis_context = {
            "original_user_input": self.request.user_input,
            "plan_scratchpad": final_plan.scratchpad,
            "tool_execution_results": execution_results,
            "verified_facts": critic_verdict.get("summary_of_facts", ""),
            "policy_graph_meta": (
                getattr(selection, "champion_arm", None)
                and selection.champion_arm.policy_graph_meta
            )
            or {},
            "arm_style": (
                getattr(selection, "champion_arm", None)
                and selection.champion_arm.policy_graph_meta
            )
            or {},
            "selected_arm_id": chosen_arm_id,
            "memory": memory_ctx,
            "memory_context_str": memory_block,
            "current_time_utc": datetime.now(UTC).isoformat(),
            "output_mode": self.request.output_mode,
        }
        expressive_text = await run_voxis_synthesis(synthesis_context)

        # --- TTS integration (voice mode) ---
        if self.request.output_mode == "voice":
            logger.info(
                "[Pipeline] Voice mode detected. Triggering TTS synthesis job.",
                extra=self.log_extra,
            )
            tts_result = await _trigger_synthesis_job(
                main_text=expressive_text, interim_text=final_plan.interim_thought
            )
            final_output = {
                "mode": "voice",
                "expressive_text": expressive_text,
                "episode_id": episode_id,
                "arm_id": chosen_arm_id,
                **tts_result,  # interim_audio_b64, full_audio_job_id, full_audio_poll_url (or error)
            }
        else:
            final_output = {
                "mode": "text",
                "expressive_text": expressive_text,
                "episode_id": episode_id,
                "arm_id": chosen_arm_id,
            }

        # ingest assistant turn & link
        resp_node_id = await ingest_turn_node(
            role="assistant",
            user_id=self.request.user_id or "user_anon",
            session_id=self.request.session_id or "unknown",
            text=expressive_text or "",
        )
        if last_input_node_id and resp_node_id:
            await link_input_to_response(last_input_node_id, resp_node_id)

        # async telemetry (always emits utility score)
        asyncio.create_task(
            self._post_turn_telem(
                episode_id=episode_id,
                task_key="voxis_conversational_turn",
                chosen_arm_id=chosen_arm_id,
                expressive_text=expressive_text,
                execution_results=execution_results,
                fact_critic_verdict=critic_verdict,
                plan=final_plan,
            ),
        )

        return final_output
