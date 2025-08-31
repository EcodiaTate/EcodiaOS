# systems/simula/agent/orchestrator_main.py
# --- AMBITIOUS UPGRADE (SYNAPSE-DRIVEN ORCHESTRATION) ---
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.prompting.orchestrator import PolicyHint, build_prompt
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.qora import api_client as qora_client
from systems.simula.agent.orchestrator.context import ContextStore
from systems.simula.agent.orchestrator.tool_safety import TOOLS
from core.services.synapse import SynapseClient
from systems.simula.config import settings
from systems.synapse.schemas import Candidate, TaskContext

logger = logging.getLogger(__name__)

def _j(obj: Any, max_len: int = 5000) -> str:
    """Safely serialize an object to a truncated JSON string for logging."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, indent=2)[:max_len]
    except Exception:
        return str(obj)[:max_len]

# --- UNCHANGED: Kept for legacy LLM call paths if needed ---
def _parse_llm_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses the LLM response, gracefully handling multiple possible JSON structures.
    It always returns a standardized dictionary with 'thought' and 'action' keys.
    """
    parsed_json = {}
    if isinstance(payload.get("json"), dict):
        parsed_json = payload["json"]
    else:
        try:
            choices = payload.get("choices", [])
            if choices and isinstance(choices, list):
                content = choices[0].get("message", {}).get("content", "")
                if isinstance(content, str) and content.strip().startswith("{"):
                    parsed_json = json.loads(content)
        except Exception:
            pass

    if not parsed_json or not isinstance(parsed_json, dict):
        return {"thought": "Error: LLM output was not valid JSON.", "action": {}}

    thought = (
        parsed_json.get("thought")
        or parsed_json.get("thoughts")
        or parsed_json.get("thought_process", "No thought provided.")
    )
    action_obj = parsed_json.get("action") or parsed_json.get("next_action")

    final_action = {}
    if isinstance(action_obj, dict):
        final_action = {
            "tool_name": action_obj.get("tool_name") or action_obj.get("tool"),
            "parameters": action_obj.get("parameters", {}),
        }
    elif "tool_name" in parsed_json or "tool" in parsed_json:
        final_action = {
            "tool_name": parsed_json.get("tool_name") or parsed_json.get("tool"),
            "parameters": parsed_json.get("parameters", {}),
        }

    return {"thought": thought, "action": final_action}

class AgentOrchestrator:
    """
    A stateful, context-driven agent orchestrator. Upgraded to be fully driven
    by the Synapse learning system, aligning with the EcodiaOS bible.
    """

    def __init__(self) -> None:
        self.ctx: ContextStore | None = None
        self.tool_registry = TOOLS
        self.tool_specs: List[Dict[str, Any]] | None = None
        self.synapse_client = SynapseClient()
        logger.debug("Orchestrator initialized with tools: %s", list(self.tool_registry.keys()))

    def _tool_specs_manifest(self) -> List[Dict[str, Any]]:
        if self.tool_specs is not None:
            return self.tool_specs
        manifest: List[Dict[str, Any]] = []
        from systems.simula.agent.tool_specs_additions import ADDITIONAL_TOOL_SPECS
        all_specs = ADDITIONAL_TOOL_SPECS
        for name in self.tool_registry.keys():
            spec = next((s for s in all_specs if s.get("name") == name), None)
            if spec:
                manifest.append(spec)
            else:
                manifest.append({"name": name, "parameters": {}})
        manifest.sort(key=lambda s: s.get("name", ""))
        self.tool_specs = manifest
        return manifest


    def _get_tool_spec(self, tool_name: str) -> Optional[Dict[str, Any]]:
        manifest = self._tool_specs_manifest()
        return next((spec for spec in manifest if spec.get("name") == tool_name), None)


    async def _get_parameters_for_tool(self, ctx: ContextStore, tool_name: str) -> dict[str, Any]:
        """
        NEW: A focused LLM call to determine *how* to use a tool that Synapse has already selected.
        This separates the strategic decision (what) from the tactical implementation (how).
        """
        ctx.set_status(f"planning_parameters_for:{tool_name}")
        tool_spec = self._get_tool_spec(tool_name)
        if not tool_spec:
            return {}

        ctx.state.setdefault("vars", {})
        ctx.state["vars"]["tool_spec_for_planning"] = tool_spec
        ctx.state.setdefault("facts", {})
        if "goal" not in ctx.state["facts"]:
            ctx.state["facts"]["goal"] = ctx.state.get("objective") or ""

        try:
            hint = PolicyHint(scope="simula.react.get_params", context=ctx.state)
            prompt_data = await build_prompt(hint)

            http = await get_http_client()
            payload = {
                "agent_name": "Simula",
                "messages": prompt_data.messages,
                "provider_overrides": {"json_mode": True, **(prompt_data.provider_overrides or {})},
                "provenance": prompt_data.provenance,
            }
            resp = await http.post(ENDPOINTS.LLM_CALL, json=payload, timeout=settings.timeouts.llm)
            resp.raise_for_status()
            
            # The response should be a JSON object containing the 'parameters'
            response_json = resp.json()
            parsed_json = response_json.get("json", {}) if isinstance(response_json.get("json"), dict) else json.loads(response_json.get("text", "{}"))
            return parsed_json.get("parameters", {})
            
        except Exception as e:
            logger.exception(f"CRITICAL: LLM parameter planning failed for tool {tool_name}.")
            ctx.add_failure("get_parameters_for_tool", f"LLM call failed: {e!r}", {"tool_name": tool_name})
            return {}

    async def _call_tool(self, tool_name: str, params: Dict[str, Any], timeout: int | None = None) -> Dict[str, Any]:
        logger.info("Calling tool=%s with params=%s", tool_name, _j(params))
        
        # --- Handle Special Orchestrator-Level Meta-Tools ---
        if tool_name == "finish":
            return {"status": "success", "result": "Finish called by agent."}

        tool_function = self.tool_registry.get(tool_name)
        if not tool_function:
            return {"status": "error", "reason": f"Unknown tool '{tool_name}'"}

        result = {}
        try:
            # NEW: Pass dynamic timeout
            tool_call = tool_function(params)
            result = await asyncio.wait_for(tool_call, timeout=timeout or settings.timeouts.tool_default)
            
            # --- LOG SUCCESSFUL REPAIRS ---
            if self.ctx and self.ctx.state.get("failures") and result.get("status") == "success" and "diff" in result.get("proposal", {}):
                last_failure = self.ctx.state["failures"][-1]
                if last_failure.get("signature"):
                    await qora_client.resolve_conflict(
                        conflict_id=last_failure["signature"],
                        successful_diff=result["proposal"]["diff"]
                    )
                    self.ctx.push_summary(f"Successfully repaired previous failure for tool: {last_failure.get('tool_name')}")

        except asyncio.TimeoutError:
            logger.warning("Tool execution timed out for tool: %s", tool_name)
            result = {"status": "error", "reason": f"Tool '{tool_name}' timed out after {timeout or settings.timeouts.tool_default}s."}
        except Exception as e:
            logger.exception("Tool execution crashed for tool: %s", tool_name)
            result = {"status": "error", "reason": f"Tool '{tool_name}' crashed with error: {e!r}"}
        
        if result.get("status") == "error" and self.ctx:
            # --- LOG FAILURES TO THE GRAPH FOR LEARNING ---
            failure_context = {
                "tool_name": tool_name, "params": params, "reason": result.get("reason"),
                "goal": self.ctx.state["facts"]["goal"]
            }
            failure_sig = hashlib.sha1(json.dumps(failure_context, sort_keys=True).encode()).hexdigest()
            await qora_client.create_conflict(
                system="Simula",
                description=f"Tool '{tool_name}' failed during goal: {failure_context['goal']}",
                signature=failure_sig,
                context=failure_context
            )
            self.ctx.add_failure(tool_name, result.get("reason"), params, signature=failure_sig)

        return result

    async def run(self, goal: str, objective_dict: Dict[str, Any], budget_ms: int | None = None) -> Dict[str, Any]:
        run_id = f"run_{int(time.time())}"
        run_dir = str(Path(settings.artifacts_root) / "runs" / run_id)
        self.ctx = ContextStore(run_dir)
        self.ctx.remember_fact("goal", goal)
        self.ctx.state["plan"] = objective_dict
        
        # NEW: Budget Awareness
        initial_budget_ms = budget_ms or (settings.timeouts.test * 1000)
        self.ctx.remember_fact("budget_ms", initial_budget_ms)
        self.ctx.remember_fact("start_time_ns", time.time_ns())

        logger.info("START job_id=%s goal='%s' budget_ms=%s", run_id, goal, initial_budget_ms)

        # --- NEW: Synapse-Driven Loop ---
        task_ctx = TaskContext(task_key="simula.code_evolution.step", goal=goal, risk_level="medium")
        tool_candidates = [Candidate(id=spec["name"], content={"description": spec.get("description", "")}) 
                           for spec in self._tool_specs_manifest()]

        for turn_num in range(settings.max_turns):
            self.ctx.remember_fact("turn", turn_num + 1)
            print(f"\n--- 🔥 TURN {turn_num + 1} / {settings.max_turns} 🔥 ---\n")
            
            # 1. Ask Synapse for the next strategic action (tool)
            self.ctx.set_status("selecting_strategy_with_synapse")
            selection = await self.synapse_client.select_arm(task_ctx, candidates=tool_candidates)
            tool_name = selection.champion_arm.arm_id
            episode_id = selection.episode_id
            
            # 2. Get Constitutional rules to guide parameter generation
            try:
                constitution_res = await qora_client.get_constitution(agent="Simula", profile="prod")
                active_rules = constitution_res.get("rules", [])
                if active_rules:
                    self.ctx.state["vars"]["constitutional_rules"] = active_rules
                    self.ctx.push_summary("Applied Constitutional Guardrails to parameter planning.")
            except Exception as e:
                logger.warning(f"Could not fetch constitution: {e!r}")
                self.ctx.state["vars"]["constitutional_rules"] = []

            # 3. Use LLM to get tactical parameters for the chosen tool
            params = await self._get_parameters_for_tool(self.ctx, tool_name)
            
            summary = f"Turn {turn_num + 1}: Synapse chose '{tool_name}'."
            self.ctx.push_summary(summary)
            print(f"STRATEGY: {tool_name}\nPARAMETERS: {_j(params, 500)}\n")

            if not tool_name:
                self.ctx.add_failure("synapse_select_arm", "Synapse did not specify a tool_name.")
                continue

            # 4. Execute the tool
            if tool_name == "finish":
                print("--- ✅ AGENT FINISHED ✅ ---\n")
                return {"status": "completed", "message": params.get("message", "Task finished by Synapse directive.")}

            self.ctx.set_status(f"executing:{tool_name}")
            # Calculate remaining budget for tool timeout
            elapsed_ms = (time.time_ns() - self.ctx.get_fact("start_time_ns", time.time_ns())) / 1_000_000
            remaining_budget_ms = initial_budget_ms - elapsed_ms
            tool_timeout_s = max(10, remaining_budget_ms / 1000) if remaining_budget_ms > 0 else 10
            
            result = await self._call_tool(tool_name, params, timeout=int(tool_timeout_s))
            print(f"RESULT: {_j(result, 2000)}\n")

            # 5. Report outcome to Synapse for learning
            utility = 1.0 if result.get("status") in ["success", "proposed", "healed", "completed"] else 0.0
            await self.synapse_client.log_outcome(
                episode_id=episode_id,
                task_key=task_ctx.task_key,
                metrics={"chosen_arm_id": tool_name, "utility": utility, "turn": turn_num + 1}
            )

            # --- Multi-agent refinement loop (Unchanged but now integrated) ---
            is_patch_proposal = tool_name == "propose_intelligent_patch" and result.get("status") == "success"
            if is_patch_proposal:
                draft_diff = result.get("proposal", {}).get("diff", "")
                if draft_diff:
                    # The rest of the critique loop from the original file...
                    self.ctx.set_status("deliberating_critique")
                    critique_result = await self._call_tool("qora_request_critique", {"diff": draft_diff})
                    critiques = critique_result.get("result", {}).get("critiques", [])
                    if critiques:
                        self.ctx.set_status("refining_patch")
                        self.ctx.push_summary(f"🔬 Received {len(critiques)} critiques. Refining patch...")
                        refinement_goal = f"""The original goal was: {goal}
An initial patch was generated but a panel of AI critics provided feedback.
Your task is to generate a new, improved patch that addresses all of their points.
CRITIC FEEDBACK:
{_j(critiques)}

ORIGINAL PATCH:
```diff
{draft_diff}
```"""
                        result = await self._call_tool("propose_intelligent_patch", {"goal": refinement_goal, "objective": {}})
                        print(f"REFINED RESULT: {_j(result, 2000)}\n")

            if result.get("status") != "error":
                observation = f"Observation from previous turn: Tool '{tool_name}' completed.\nOutput: {_j(result, 1500)}"
                self.ctx.push_summary(observation)
            
            await asyncio.sleep(1)

        print("--- ❌ AGENT TIMEOUT ❌ ---\n")
        return {"status": "failed", "reason": "Agent exceeded maximum number of turns"}