# systems/simula/agent/scl_utils.py
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service, extract_json_flex
from core.utils.neo.cypher_query import cypher_query
from systems.synapse.schemas import ArmScore

# NEW: run logger for structured traces
from .runlog import RunLogger

log = logging.getLogger(__name__)

# ------------------------------- ID / Hashing -------------------------------


def _canonical_json(obj: Any) -> str:
    """Creates a stable, sorted JSON string from an object."""
    try:
        if hasattr(obj, "model_dump"):
            obj = obj.model_dump(mode="json")
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return json.dumps({"_repr": str(obj)})


def _sha16_for(obj: Any) -> str:
    """Generates a short SHA256 hash for an object."""
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()[:16]


# ------------------------------- FQN Parsing -------------------------------


def _path_from_fqname(target_fqname: str | None) -> str | None:
    """'path/to/file.py::my_func' -> 'path/to/file.py'"""
    return (target_fqname.split("::", 1)[0] or None) if target_fqname else None


def _func_from_fqname(target_fqname: str | None) -> str | None:
    """'path/to/file.py::my_func' -> 'my_func'"""
    if not target_fqname or "::" not in target_fqname:
        return None
    return target_fqname.split("::", 1)[1] or None


# ------------------------------- Plan Shaping & Injection -------------------------------


def _coerce_plan_steps(raw_plan: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_plan, list):
        return []
    steps: list[dict[str, Any]] = []
    for s in raw_plan:
        if not isinstance(s, dict):
            continue
        kind = s.get("action_type")
        if kind == "tool_call":
            steps.append(
                {
                    "action_type": "tool_call",
                    "tool_name": s.get("tool_name"),
                    "parameters": s.get("parameters")
                    if isinstance(s.get("parameters"), dict)
                    else {},
                }
            )
        elif kind == "respond":
            # keep simple response payload if provided
            steps.append(
                {
                    "action_type": "respond",
                    "parameters": {
                        "content": s.get("content") or s.get("message") or s.get("text") or "",
                    },
                }
            )
    return steps


def _inject_target_defaults(
    params: dict[str, Any], *, tool_name: str, target_fqname: str | None
) -> dict[str, Any]:
    if not target_fqname:
        return params

    path = _path_from_fqname(target_fqname)
    func = _func_from_fqname(target_fqname)

    if tool_name in {"read_file", "write_file", "delete_file"}:
        if path and "path" not in params:
            params["path"] = path

    elif tool_name in {
        "run_tests",
        "run_tests_k",
        "run_tests_xdist",
        "run_tests_and_diagnose_failures",  # <— add this
        "run_repair_engine",
        "static_check",
        "format_patch",
    }:
        if path and "paths" not in params:
            params["paths"] = [path]

    elif tool_name in {"run_fuzz_smoke", "generate_property_test", "debug_with_runtime_trace"}:
        if path and "module" not in params:
            params["module"] = path.replace("/", ".").removesuffix(".py")
        if func and "function" not in params:
            params["function"] = func

    return params


async def register_dynamic_arm_in_graph(arm_id: str, mode: str):
    """Merges a dynamic arm node into the graph for analytics."""
    try:
        await cypher_query(
            """
            MERGE (a:PolicyArm {id: $id})
            ON CREATE SET a.created_ts = timestamp(), a.dynamic = true, a.mode = $mode
            ON MATCH SET a.dynamic = true
            """,
            {"id": arm_id, "mode": mode},
        )
    except Exception as e:
        log.warning("[SCL] Graph registration for dynamic arm '%s' failed: %r", arm_id, e)


# ------------------------------- Scoring & Result Extraction -------------------------------


def _extract_final_diff_from_results(results: dict[str, Any]) -> str:
    """Heuristically extracts the most likely unified diff from tool execution results."""
    candidates = []
    if not isinstance(results, dict):
        return ""
    for outcome in results.values():
        if not isinstance(outcome, dict):
            continue
        if res := outcome.get("result"):
            if isinstance(res, dict):
                for k in ("diff", "patch"):
                    if isinstance(v := res.get(k), str) and "--- a/" in v:
                        candidates.append(v)
    return max(candidates, key=len) if candidates else ""


def _extract_verification_results(results: dict[str, Any]) -> dict[str, Any]:
    """Extracts summaries from test, lint, or analysis tools."""
    if not isinstance(results, dict):
        return {}
    for outcome in results.values():
        if isinstance(outcome, dict) and isinstance(res := outcome.get("result"), dict):
            for k in ("test_results", "verification_results", "diagnostics", "review"):
                if v := res.get(k):
                    return {"source": k, "payload": v}
    return {}


async def _run_utility_scorer(
    *,
    goal: str,
    dossier: dict[str, Any],
    plan: dict[str, Any],
    execution_results: dict[str, Any],
    final_diff: str,
    verification_results: dict[str, Any],
    runlog: RunLogger | None = None,  # NEW: optional structured logger
) -> dict[str, Any]:
    """
    Runs the Simula Utility Scorer with full turn context for intelligent evaluation.
    Now logs the scorer LLM prompt & completion to the run file when a RunLogger is provided.
    """
    context = {
        "goal": goal,
        "initial_context": {"dossier_provided": bool(dossier)},
        "agent_plan": plan,
        "tool_outcomes": execution_results,
        "final_diff": final_diff,
        "verification_summary": verification_results,
    }
    try:
        prompt = await build_prompt(
            scope="simula.utility_scorer",
            context=context,
            summary="Score the code evolution turn.",
        )
        resp = await call_llm_service(
            prompt,
            agent_name="Simula.UtilityScorer",
            scope="simula.utility_scorer",
            timeout=45.0,
        )
        text = getattr(resp, "text", "")
        data = extract_json_flex(text)

        # --- NEW: runlog entry for scorer LLM ---
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
                phase="utility_scorer",
                scope="simula.utility_scorer",
                agent="Simula.UtilityScorer",
                prompt_preview=preview,
                prompt_struct=getattr(prompt, "model_dump", lambda **_: None)()
                if hasattr(prompt, "model_dump")
                else None,
                completion_text=text,
                extra={"parsed_keys": list(data.keys()) if isinstance(data, dict) else []},
            )
        # --- END runlog ---

        if isinstance(data, dict) and "utility_score" in data:
            score = float(data.get("utility_score", 0.5))
            data["utility_score"] = max(0.0, min(1.0, score))
            return data
        return {"utility_score": 0.5, "reasoning": "Scorer returned invalid format."}
    except Exception as e:
        log.error("[SCL] Utility Scorer failed: %r", e, exc_info=True)
        if runlog:
            runlog.log_llm(
                phase="utility_scorer",
                scope="simula.utility_scorer",
                agent="Simula.UtilityScorer",
                prompt_preview="(exception)",
                prompt_struct=None,
                completion_text=f"(error) {e!r}",
                extra={"crashed": True},
            )
        return {"utility_score": 0.5, "reasoning": f"Utility Scorer crashed: {e}"}
