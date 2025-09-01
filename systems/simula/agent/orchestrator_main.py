# systems/simula/agent/orchestrator_main.py
# --- AMBITIOUS UPGRADE (SYNAPSE-DRIVEN ORCHESTRATION) ---
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import difflib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# Planner/JSON-noise keys we never want to forward to tools
NOISE_KEYS: set[str] = {
    "type", "$schema", "returns", "additionalProperties", "properties", "required"
}

# Fallback allowlists when a tool spec lacks a schema
ALLOWED_FALLBACK_KEYS: dict[str, set[str]] = {
    "write_code": {"path", "content"},
    "write_file": {"path", "content"},
    "apply_refactor": {"diff", "verify_paths", "base"},
    "apply_refactor_smart": {"dossier", "diff", "verify_paths", "base"},
    "rebase_patch": {"diff", "base"},
    "read_file": {"path"},
    "run_tests": {"paths", "timeout_sec"},
    "run_tests_k": {"paths", "k", "timeout_sec"},
    "run_tests_xdist": {"paths", "xdist", "timeout_sec"},
    "get_context_dossier": {"target_fqname", "intent", "top_k"},
    "finish": {"message"},
}


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
            "parameters": action_obj.get("parameters", {})
        }
    elif "tool_name" in parsed_json or "tool" in parsed_json:
        final_action = {
            "tool_name": parsed_json.get("tool_name") or parsed_json.get("tool"),
            "parameters": parsed_json.get("parameters", {})
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

        # Only allow these tools as Synapse candidates (safe, patch-based or read-only)
        # Add/remove here as your registry evolves.
        self._safe_tools: set[str] = {
            # patch-based & helpers
            "apply_refactor", "apply_refactor_smart", "rebase_patch", "format_patch", "local_select_patch",
            # context & read
            "get_context_dossier", "read_file",
            # execution
            "run_tests", "run_tests_k", "run_tests_xdist",
            # meta
            "finish",
        }

    # ----------------------- Tool Specs -----------------------

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

    # ---------------- Param normalization & safe redirects ----------------

    @staticmethod
    def _extract_paths_from_unified_diff(diff_text: str) -> list[str]:
        """
        Heuristic: pull 'b/<path>' from unified diff headers +++ b/...
        Falls back to 'a/<path>' if +++ is missing.
        """
        paths = []
        if not isinstance(diff_text, str):
            return paths
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                paths.append(line[6:].strip())
            elif not paths and line.startswith("--- a/"):
                paths.append(line[6:].strip())
        return [p for p in paths if p]

    def _normalize_and_maybe_redirect(
        self,
        ctx: ContextStore,
        tool_name: str,
        raw_params: dict[str, Any] | None,
        schema: dict[str, Any] | None
    ) -> Tuple[str, dict[str, Any]]:
        """
        Normalize planner params and, if needed, redirect unsafe 'raw writes'
        (write_code/write_file) into a diff-based patch tool.

        Returns (effective_tool_name, normalized_params).
        """
        params: dict[str, Any] = dict(raw_params or {})

        # Drop schema-ish noise the planner sometimes emits
        for k in list(params.keys()):
            if k in NOISE_KEYS:
                params.pop(k, None)

        tn = (tool_name or "").lower()

        # If the planner returned a schema-stub (now stripped) and no real fields,
        # treat as empty so we don't pass junk through to tools.
        if not params:
            # keep empty; required checks later will penalize and retry
            pass

        # Common synonyms / coercions
        if tn in {"write_code", "write_file"}:
            # Normalize content field
            if "content" not in params:
                for alt in ("code", "body", "text"):
                    if alt in params:
                        params["content"] = params.pop(alt)
                        break

            path = params.get("path")
            new_content = params.get("content")

            # If we have enough info, generate a unified diff and redirect to patch application
            if path and new_content is not None:
                try:
                    old = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
                except Exception:
                    old = ""
                diff = "".join(
                    difflib.unified_diff(
                        old.splitlines(keepends=True),
                        str(new_content).splitlines(keepends=True),
                        fromfile=f"a/{path}",
                        tofile=f"b/{path}",
                    )
                )
                # Stash a tiny file snapshot hint (not the whole file) for observability
                try:
                    vs = ctx.state.setdefault("vars", {}).setdefault("file_snapshots", {})
                    vs[path] = {"had_file": bool(old), "before_len": len(old)}
                except Exception:
                    pass

                # Safer: execute via patch applier
                return "apply_refactor", {"diff": diff, "verify_paths": [path]}
            # else: fall through; required validation below will penalize and retry

        elif tn in {"apply_refactor", "rebase_patch", "apply_refactor_smart"}:
            # Keep only recognized keys for patch tools
            keep = {"diff", "base", "verify_paths"}
            params = {k: v for k, v in params.items() if k in keep}

        elif tn in {"run_tests", "run_tests_k", "run_tests_xdist"}:
            # Accept 'path' -> 'paths'
            if "paths" not in params and "path" in params:
                params["paths"] = [params.pop("path")]
            # Filter out non-existent paths; if none remain, drop 'paths' to allow default discovery
            if "paths" in params:
                _paths = [p for p in (params.get("paths") or []) if isinstance(p, str) and p.strip()]
                existing: list[str] = []
                for p in _paths:
                    try:
                        if Path(p).exists():
                            existing.append(p)
                    except Exception:
                        pass
                if existing:
                    params["paths"] = existing
                else:
                    params.pop("paths", None)

        elif tn in {"get_context_dossier"}:
            # Always provide an intent; prefer job plan, else default
            if "intent" not in params:
                intent = (ctx.state.get("plan") or {}).get("intent") or "codeedit"
                params["intent"] = intent

        # Trim to schema properties (if any)
        props = list((schema or {}).get("properties", {}).keys())
        if props:
            params = {k: v for k, v in params.items() if k in props}
        else:
            # No schema in spec? Apply a cautious allowlist per tool.
            allowed = ALLOWED_FALLBACK_KEYS.get(tn)
            if allowed is not None:
                params = {k: v for k, v in params.items() if k in allowed}
        return tool_name, params

    async def _get_parameters_for_tool(self, ctx: ContextStore, tool_name: str) -> Tuple[str, dict[str, Any]]:
        """
        Determine parameters for a selected tool via the param-planner PromptSpec.

        Returns (effective_tool_name, params) where the tool may be safely redirected
        (e.g., write_code -> apply_refactor) after computing a unified diff.
        """
        ctx.set_status(f"planning_parameters_for:{tool_name}")
        tool_spec = self._get_tool_spec(tool_name)
        if not tool_spec:
            logger.warning("No tool spec found for %s; returning empty params.", tool_name)
            return tool_name, {}

        # ---- Ensure planning context is populated for the template
        vars_ = ctx.state.setdefault("vars", {})
        vars_["tool_spec_for_planning"] = tool_spec

        facts = ctx.state.setdefault("facts", {})
        if "goal" not in facts:
            facts["goal"] = ctx.state.get("objective") or ""

        # Put top-level keys the template expects
        ctx.state["goal"] = facts["goal"]
        ctx.state["tool_name"] = tool_name
        schema: dict[str, Any] = tool_spec.get("parameters") or {"type": "object", "additionalProperties": True}
        ctx.state["schema_json"] = json.dumps(schema)

        try:
            # --- Build prompt
            hint = PolicyHint(scope="simula.react.get_params", context=ctx.state)
            prompt_data = await build_prompt(hint)

            # --- Call LLM
            http = await get_http_client()
            payload = {
                "agent_name": "Simula",
                "messages": prompt_data.messages,
                "provider_overrides": {"json_mode": True, **(getattr(prompt_data, "provider_overrides", None) or {})},
                "provenance": getattr(prompt_data, "provenance", None),
            }
            resp = await http.post(ENDPOINTS.LLM_CALL, json=payload, timeout=settings.timeouts.llm)
            resp.raise_for_status()

            # Planner contract: parameters object itself
            data = resp.json()
            if isinstance(data.get("json"), dict):
                raw_params = data["json"]
            else:
                raw_params = json.loads(data.get("text", "{}") or "{}")

            effective_tool, params = self._normalize_and_maybe_redirect(ctx, tool_name, raw_params, schema)

            # Light validation against "required" if present
            required = (schema or {}).get("required") or []
            missing = [k for k in required if k not in params]

            # Extra guardrails for raw write tools even if spec forgot 'required'
            if not missing and (tool_name in {"write_code", "write_file"}):
                if "path" not in params or "content" not in params:
                    missing = [x for x in ("path", "content") if x not in params]

            if missing and effective_tool == tool_name:
                # Only penalize if we didn't redirect; the redirect may change requireds
                raise ValueError(f"planner_missing_required: {missing}")

            # Small breadcrumb for observability
            ctx.push_summary(f"Param plan for {tool_name}→{effective_tool}: keys={list(params.keys())[:6]}")

            return effective_tool, params

        except Exception as e:
            logger.exception("CRITICAL: LLM parameter planning failed for tool %s.", tool_name)
            ctx.add_failure("get_parameters_for_tool", f"LLM call failed: {e!r}", {"tool_name": tool_name})
            return tool_name, {}

    # ---------------------- Tool calling & conflict wiring ----------------------

    async def _call_tool(self, tool_name: str, params: Dict[str, Any], timeout: int | None = None) -> Dict[str, Any]:
        # Final safety scrub: never forward schema noise to tools,
        # even if something slipped past earlier normalization.
        if params:
            for k in list(params.keys()):
                if k in NOISE_KEYS:
                    params.pop(k, None)

        # Optional: prune to fallback allowlist when spec is loose.
        allowed = ALLOWED_FALLBACK_KEYS.get(tool_name.lower())
        if allowed is not None:
            params = {k: v for k, v in params.items() if k in allowed}
        logger.info("Calling tool=%s with params=%s", tool_name, _j(params))

        # --- Handle Special Orchestrator-Level Meta-Tools ---
        if tool_name == "finish":
            return {"status": "success", "result": "Finish called by agent."}

        tool_function = self.tool_registry.get(tool_name)
        if not tool_function:
            return {"status": "error", "reason": f"Unknown tool '{tool_name}'"}

        result: Dict[str, Any] | None = None
        try:
            tool_call = tool_function(params)
            result = await asyncio.wait_for(tool_call, timeout=timeout or settings.timeouts.tool_default)

            # Guard: never bubble None
            if result is None:
                result = {"status": "error", "reason": f"Tool '{tool_name}' returned None"}

            # --- LOG SUCCESSFUL REPAIRS ---
            if self.ctx and self.ctx.state.get("failures") and result.get("status") in {"success", "healed", "completed"}:
                # Try to find a diff in common shapes
                diff: Optional[str] = None
                if isinstance(result.get("proposal"), dict):
                    diff = result["proposal"].get("diff")
                if diff is None and isinstance(result.get("result"), dict):
                    diff = result["result"].get("diff") or (result["result"].get("proposal") or {}).get("diff")
                if diff is None:
                    diff = result.get("diff")

                if diff:
                    last_failure = self.ctx.state["failures"][-1]
                    conflict_id = last_failure.get("conflict_id") or last_failure.get("signature")
                    if conflict_id:
                        try:
                            await qora_client.resolve_conflict(conflict_id=conflict_id, successful_diff=diff)
                        except Exception as _e:
                            logger.warning("resolve_conflict failed (non-fatal): %r", _e)
                        else:
                            self.ctx.push_summary(
                                f"Successfully repaired previous failure for tool: {last_failure.get('tool_name')}"
                            )

        except asyncio.TimeoutError:
            logger.warning("Tool execution timed out for tool: %s", tool_name)
            result = {"status": "error", "reason": f"Tool '{tool_name}' timed out after {timeout or settings.timeouts.tool_default}s."}
        except Exception as e:
            logger.exception("Tool execution crashed for tool: %s", tool_name)
            result = {"status": "error", "reason": f"Tool '{tool_name}' crashed with error: {e!r}"}

        # Failure wiring → conflict graph
        if result.get("status") == "error" and self.ctx:
            failure_context = {
                "tool_name": tool_name,
                "params": params,
                "reason": result.get("reason"),
                "goal": self.ctx.state.get("facts", {}).get("goal"),
            }
            failure_sig = hashlib.sha1(json.dumps(failure_context, sort_keys=True).encode()).hexdigest()

            conflict_uuid = None
            try:
                api_res = await qora_client.create_conflict(
                    system="Simula",
                    description=f"Tool '{tool_name}' failed during goal: {failure_context.get('goal')}",
                    signature=failure_sig,
                    context=failure_context,
                )
                # Try to extract the canonical conflict UUID if helper exists
                extractor = getattr(qora_client, "extract_conflict_uuid", None)
                if callable(extractor):
                    conflict_uuid = extractor(api_res)
            except Exception as e:
                logger.warning("create_conflict failed (non-fatal): %r", e)

            # Record failure locally
            self.ctx.add_failure(tool_name, result.get("reason"), params)
            try:
                self.ctx.state.setdefault("failures", [])
                if self.ctx.state["failures"]:
                    self.ctx.state["failures"][-1]["signature"] = failure_sig
                    if conflict_uuid:
                        self.ctx.state["failures"][-1]["conflict_id"] = conflict_uuid
            except Exception:
                pass

        return result or {"status": "error", "reason": "Unknown tool result"}

    # ------------------------------- Main loop -------------------------------

    async def run(self, goal: str, objective_dict: Dict[str, Any], budget_ms: int | None = None) -> Dict[str, Any]:
        run_id = f"run_{int(time.time())}"
        run_dir = str(Path(settings.artifacts_root) / "runs" / run_id)
        self.ctx = ContextStore(run_dir)
        self.ctx.remember_fact("goal", goal)
        self.ctx.state["plan"] = objective_dict

        # --- Dossier prefetch & confirmation ---
        try:
            dossier: Dict[str, Any] = {}
            tgt = (objective_dict or {}).get("target_fqname")
            intent = (objective_dict or {}).get("intent") or "codeedit"
            if tgt:
                dossier = await qora_client.get_dossier(target_fqname=tgt, intent=intent)
            else:
                dossier = await qora_client.get_goal_context(goal, top_k=5)
            self.ctx.update_dossier(dossier or {})
            items = (dossier or {}).get("items") or (dossier or {}).get("results") or []
            logger.info("[Dossier] Ready with %s items.", len(items))
            self.ctx.push_summary(f"Dossier ready with {len(items)} items.")
        except Exception as e:
            logger.warning("[Dossier] fetch failed (non-fatal): %r", e)

        # Budget Awareness
        initial_budget_ms = budget_ms or (settings.timeouts.test * 1000)
        self.ctx.remember_fact("budget_ms", initial_budget_ms)
        self.ctx.remember_fact("start_time_ns", time.time_ns())

        logger.info("START job_id=%s goal='%s' budget_ms=%s", run_id, goal, initial_budget_ms)

        # --- Synapse-Driven Loop ---
        task_ctx = TaskContext(task_key="simula.code_evolution.step", goal=goal, risk_level="medium")

        # Only expose safe tools to Synapse as candidates (must exist in registry)
        manifest = self._tool_specs_manifest()
        tool_candidates = [
            Candidate(id=spec["name"], content={"description": spec.get("description", "")})
            for spec in manifest
            if spec.get("name") in self._safe_tools and spec.get("name") in self.tool_registry
        ]

        allowed_tools = {c.id for c in tool_candidates} | {"finish"}

        for turn_num in range(settings.max_turns):
            self.ctx.remember_fact("turn", turn_num + 1)
            print(f"\n--- 🔥 TURN {turn_num + 1} / {settings.max_turns} 🔥 ---\n")

            # 1) Choose strategy (tool)
            self.ctx.set_status("selecting_strategy_with_synapse")
            selection = await self.synapse_client.select_arm(task_ctx, candidates=tool_candidates)
            raw_choice = selection.champion_arm.arm_id
            tool_name = raw_choice if raw_choice in allowed_tools else "get_context_dossier"
            episode_id = selection.episode_id

            # 2) Fetch constitution (guardrails)
            try:
                self.ctx.state.setdefault("vars", {})
                constitution_res = await qora_client.get_constitution(agent="Simula", profile="prod")
                active_rules = constitution_res.get("rules", [])
                if active_rules:
                    self.ctx.state["vars"]["constitutional_rules"] = active_rules
                    self.ctx.push_summary("Applied Constitutional Guardrails to parameter planning.")
            except Exception as e:
                logger.warning("Could not fetch constitution: %r", e)
                self.ctx.state.setdefault("vars", {})["constitutional_rules"] = []

            # 3) Plan params (may redirect tool)
            tool_name_eff, params = await self._get_parameters_for_tool(self.ctx, tool_name)

            # Validate again (defensive) before executing
            spec = self._get_tool_spec(tool_name_eff) or {}
            required = (spec.get("parameters") or {}).get("required") or []
            missing = [k for k in required if k not in (params or {})]
            if missing:
                reason = f"Planner did not supply required fields: {missing}"
                self.ctx.add_failure("parameter_validation", reason, {"tool_name": tool_name_eff})
                print(f"STRATEGY: {tool_name}→{tool_name_eff}\nPARAMETERS: {_j(params, 500)}\n")
                print(f"RESULT: {reason}\n")
                await self.synapse_client.log_outcome(
                    episode_id=episode_id,
                    task_key=task_ctx.task_key,
                    metrics={"chosen_arm_id": tool_name_eff, "utility": 0.0, "turn": turn_num + 1},
                )
                await asyncio.sleep(1)
                continue

            # 🧪 Preflight: before any write/patch tool, make sure content is loaded
            if tool_name_eff in {"apply_refactor", "apply_refactor_smart", "rebase_patch"}:
                verify_paths: List[str] = []
                vp = params.get("verify_paths")
                if isinstance(vp, list):
                    verify_paths = [p for p in vp if isinstance(p, str)]
                if not verify_paths and isinstance(params.get("diff"), str):
                    verify_paths = self._extract_paths_from_unified_diff(params["diff"])

                preflight_failed = False
                for p in verify_paths[:10]:
                    cache_key = f"file:{p}"
                    if self.ctx.cache_get(cache_key) is None:
                        rf = await self._call_tool("read_file", {"path": p}, timeout=10)
                        if rf.get("status") == "success":
                            try:
                                content = rf["result"]["content"]
                            except Exception:
                                content = None
                            if isinstance(content, str):
                                self.ctx.cache_put(cache_key, content, ttl_sec=3600)
                        else:
                            self.ctx.add_failure(tool_name_eff, f"Preflight read failed for {p}", {"path": p})
                            preflight_failed = True
                if preflight_failed:
                    await self.synapse_client.log_outcome(
                        episode_id=episode_id,
                        task_key=task_ctx.task_key,
                        metrics={"chosen_arm_id": tool_name_eff, "utility": 0.0, "turn": turn_num + 1},
                    )
                    await asyncio.sleep(0.5)
                    continue

            summary = f"Turn {turn_num + 1}: Synapse chose '{raw_choice}' → executing '{tool_name_eff}'."
            self.ctx.push_summary(summary)
            print(f"STRATEGY: {tool_name}→{tool_name_eff}\nPARAMETERS: {_j(params, 500)}\n")

            if not tool_name_eff:
                self.ctx.add_failure("synapse_select_arm", "Synapse did not specify a tool_name.")
                continue

            # 4) Execute
            if tool_name_eff == "finish":
                print("--- ✅ AGENT FINISHED ✅ ---\n")
                return {"status": "completed", "message": params.get("message", "Task finished by Synapse directive.")}

            self.ctx.set_status(f"executing:{tool_name_eff}")
            elapsed_ms = (time.time_ns() - self.ctx.get_fact("start_time_ns", time.time_ns())) / 1_000_000
            remaining_budget_ms = initial_budget_ms - elapsed_ms
            tool_timeout_s = max(10, remaining_budget_ms / 1000) if remaining_budget_ms > 0 else 10

            result = await self._call_tool(tool_name_eff, params, timeout=int(tool_timeout_s))
            print(f"RESULT: {_j(result, 2000)}\n")

            # 5) Report outcome to Synapse
            status_str = (result or {}).get("status")
            utility = 1.0 if status_str in ["success", "proposed", "healed", "completed"] else 0.0
            await self.synapse_client.log_outcome(
                episode_id=episode_id,
                task_key=task_ctx.task_key,
                metrics={"chosen_arm_id": tool_name_eff, "utility": utility, "turn": turn_num + 1},
            )

            # --- Optional refinement loop (propose → critique → refine) ---
            is_patch_proposal = tool_name_eff == "propose_intelligent_patch" and (result or {}).get("status") == "success"
            if is_patch_proposal:
                draft_diff = (result or {}).get("proposal", {}).get("diff", "")
                if draft_diff:
                    self.ctx.set_status("deliberating_critique")
                    critique_result = await self._call_tool("qora_request_critique", {"diff": draft_diff})
                    critiques = (critique_result.get("result") or {}).get("critiques", [])

                    if critiques:
                        self.ctx.set_status("refining_patch")
                        self.ctx.push_summary(f"🔬 Received {len(critiques)} critiques. Refining patch...")

                        try:
                            hint_ctx = {"goal": goal, "critiques": critiques, "draft_diff": draft_diff, **self.ctx.state}
                            prompt = await build_prompt(PolicyHint(scope="simula.react.refine_patch", context=hint_ctx))

                            http = await get_http_client()
                            payload = {
                                "agent_name": "Simula",
                                "messages": prompt.messages,
                                "provider_overrides": {"json_mode": True, **(getattr(prompt, "provider_overrides", None) or {})},
                                "provenance": getattr(prompt, "provenance", None),
                            }
                            resp = await http.post(ENDPOINTS.LLM_CALL, json=payload, timeout=settings.timeouts.llm)
                            resp.raise_for_status()
                            data = resp.json()
                            refined = data.get("json") if isinstance(data.get("json"), dict) else json.loads(data.get("text", "{}") or "{}")
                            refined_diff = (refined or {}).get("diff", "")

                            if isinstance(refined_diff, str) and refined_diff.startswith("--- a/"):
                                apply_res = await self._call_tool("rebase_patch", {"diff": refined_diff, "base": "main"})
                                print(f"REFINED RESULT: {_j(apply_res, 2000)}\n")
                                result = apply_res
                            else:
                                self.ctx.add_failure("refine_patch", "Planner did not return a valid unified diff.", {"critiques": critiques})
                                await self.synapse_client.log_outcome(
                                    episode_id=episode_id,
                                    task_key=task_ctx.task_key,
                                    metrics={"chosen_arm_id": "refine_patch", "utility": 0.0, "turn": turn_num + 1},
                                )
                        except Exception as e:
                            logger.warning("Refinement step failed (non-fatal): %r", e)

            if (result or {}).get("status") != "error":
                observation = f"Observation from previous turn: Tool '{tool_name_eff}' completed.\nOutput: {_j(result, 1500)}"
                self.ctx.push_summary(observation)

            await asyncio.sleep(1)

        print("--- ❌ AGENT TIMEOUT ❌ ---\n")
        return {"status": "failed", "reason": "Agent exceeded maximum number of turns"}
