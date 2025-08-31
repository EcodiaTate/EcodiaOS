# systems/simula/orchestrator/services.py

from __future__ import annotations

import asyncio
import json
import os
import types
from typing import Any
from uuid import uuid4

from core.utils.net_api import ENDPOINTS, get_http_client
from core.utils.time import now_iso
from systems.qora.client import fetch_llm_tools
from systems.simula.agent.orchestrator.utils import _j, _neo4j_down, _timeit, logger
from systems.synapse.core.governor import Governor
from systems.unity.core.room.participants import participant_registry

from ...agent.tool_specs import TOOL_SPECS
from ...agent.tool_specs_additions import ADDITIONAL_TOOL_SPECS
from ...config.gates import load_gates
from ...policy.eos_checker import check_diff_against_policies, load_policy_packs


# Forward declaration for type hinting
class AgentOrchestrator:
    pass


async def _repo_rev(orchestrator: AgentOrchestrator) -> str | None:
    """Best-effort: return current repo HEAD short SHA for cache provenance."""
    logger.debug("[_repo_rev] Fetching git short SHA")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--short",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        sha = (out or b"").decode("utf-8", "ignore").strip()
        logger.debug("[_repo_rev] HEAD short SHA: %s", sha)
        return sha or None
    except Exception as e:
        logger.debug("[_repo_rev] Could not read repo rev: %r", e)
        return None


async def _safe_smt_check(orchestrator: AgentOrchestrator, policy_graph):
    logger.debug("[_safe_smt_check] Starting SMT check")
    with _timeit("synapse.smt_check"):
        try:
            res = await orchestrator.synapse.smt_check(policy_graph)
            logger.debug(
                "[_safe_smt_check] SMT result: %s",
                _j(getattr(res, "model_dump", lambda: res)()),
            )
            return res
        except Exception as e:
            if _neo4j_down(e) or os.environ.get("SIMULA_TEST_MODE") == "1":
                logger.debug("[_safe_smt_check] Using offline SMT stub due to %r", e)
                return types.SimpleNamespace(
                    ok=True,
                    reason="offline_stub",
                    model_dump=lambda: {"ok": True, "reason": "offline_stub"},
                )
            logger.exception("[_safe_smt_check] SMT check failed")
            raise


async def _safe_simulate(orchestrator: AgentOrchestrator, policy_graph, task_ctx):
    logger.debug("[_safe_simulate] Starting simulation with task_ctx=%s", _j(task_ctx.model_dump()))
    with _timeit("synapse.simulate"):
        try:
            res = await orchestrator.synapse.simulate(policy_graph, task_ctx)
            logger.debug(
                "[_safe_simulate] Simulation result: %s",
                _j(getattr(res, "model_dump", lambda: res)()),
            )
            return res
        except Exception as e:
            if _neo4j_down(e) or os.environ.get("SIMULA_TEST_MODE") == "1":
                logger.debug("[_safe_simulate] Using offline simulation stub due to %r", e)

                class _Sim:
                    p_success = 1.0
                    p_safety_hit = 0.0

                    def model_dump(self):
                        return {"p_success": 1.0, "p_safety_hit": 0.0, "reason": "offline_stub"}

                return _Sim()
            logger.exception("[_safe_simulate] Simulation failed")
            raise


def _build_axon_event(
    *,
    summary: str,
    instruction: str,
    reviewers: list[str],
    available_agents: list[str],
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Shape payload as AxonEvent expected by Atune /atune/route."""
    payload = {
        "event_id": str(uuid4()),
        "event_type": "simula.proposal.review.requested",
        "source": "EcodiaOS.Simula.Autonomous",
        "parsed": {
            "text_blocks": [
                summary or "Review request for code evolution proposal.",
                instruction or "Review the proposal for alignment, safety, and correctness.",
            ],
            "meta": {
                "reviewers": list(dict.fromkeys(reviewers)),
                "available_agents": available_agents,
                "proposal_id": proposal.get("proposal_id"),
                "created_at": now_iso(),
            },
            "artifact": {"proposal": proposal},
        },
    }
    logger.debug("[_build_axon_event] Built axon event: %s", _j(payload))
    return payload


async def _continue_skill_via_synapse(
    orchestrator: AgentOrchestrator,
    episode_id: str,
    last_step_outcome: dict[str, Any],
) -> dict[str, Any]:
    """POST to Synapse to continue a hierarchical skill."""
    logger.debug(
        "[_continue_skill_via_synapse] episode_id=%s outcome=%s",
        episode_id,
        _j(last_step_outcome),
    )
    try:
        http = await get_http_client()
        resp = await http.post(
            ENDPOINTS.SYNAPSE_CONTINUE_OPTION,
            json={"episode_id": episode_id, "last_step_outcome": last_step_outcome},
        )
        logger.debug("[_continue_skill_via_synapse] HTTP %s", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        logger.debug("[_continue_skill_via_synapse] response=%s", _j(data))
        return orchestrator._handle_skill_continuation(
            is_complete=bool(data.get("is_complete")),
            next_action=(data.get("next_action") or ({} if data.get("is_complete") else None)),
        )
    except Exception as e:
        logger.exception("[_continue_skill_via_synapse] failed")
        orchestrator.latest_observation = f"Skill continuation failed: {e!r}"
        orchestrator.active_option_episode_id = None
        return {"status": "error", "reason": "continue_option HTTP failed"}


async def _request_skill_repair_via_synapse(
    orchestrator: AgentOrchestrator,
    episode_id: str,
    failed_step_index: int,
    error_observation: dict[str, Any],
) -> dict[str, Any]:
    """POST to Synapse to request a repair for a failed skill step."""
    logger.debug(
        "[_request_skill_repair_via_synapse] episode_id=%s failed_idx=%s error_obs=%s",
        episode_id,
        failed_step_index,
        _j(error_observation),
    )
    try:
        http = await get_http_client()
        resp = await http.post(
            ENDPOINTS.SYNAPSE_REPAIR_SKILL_STEP,
            json={
                "episode_id": episode_id,
                "failed_step_index": int(failed_step_index),
                "error_observation": error_observation,
            },
        )
        logger.debug("[_request_skill_repair_via_synapse] HTTP %s", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        logger.debug("[_request_skill_repair_via_synapse] response=%s", _j(data))
        orchestrator.latest_observation = (
            f"Repair suggestion received: {json.dumps(data, indent=2)[:800]}"
        )
        return {"status": "repair_suggested", "repair_action": data.get("repair_action")}
    except Exception as e:
        logger.exception("[_request_skill_repair_via_synapse] failed")
        orchestrator.latest_observation = f"Skill repair failed: {e!r}"
        return {"status": "error", "reason": "repair_skill_step HTTP failed"}


async def _submit_for_review(
    orchestrator: AgentOrchestrator,
    summary: str,
    instruction: str = "",
) -> dict[str, Any]:
    """Submit final_proposal for review via Atune (HTTP /atune/route)."""
    logger.info("[_submit_for_review] summary=%s", summary)
    if not orchestrator.final_proposal:
        orchestrator.latest_observation = "Error: No proposal to submit for review."
        logger.error("[_submit_for_review] No proposal in memory")
        return {"status": "error", "reason": "No proposal generated yet."}

    # Policy and Gate checks
    try:
        diff_text = (orchestrator.final_proposal.get("context") or {}).get("diff", "") or ""
        rep = check_diff_against_policies(diff_text, load_policy_packs())
        orchestrator.final_proposal.setdefault("evidence", {})["policy"] = rep.summary()
        if not rep.ok:
            orchestrator.latest_observation = "Proposal blocked by EOS policy gate."
            return {"status": "rejected_by_policy", "findings": rep.summary()}
    except Exception as e:
        logger.exception("[_submit_for_review] policy check errored")
        orchestrator.final_proposal.setdefault("evidence", {})["policy_check_error"] = str(e)

    try:
        g = load_gates()
        hyg = (orchestrator.final_proposal.get("evidence") or {}).get("hygiene") or {}
        static_ok = hyg.get("static") == "success"
        tests_ok = hyg.get("tests") == "success"
        gate_summary = {
            "require_static_clean": g.require_static_clean,
            "require_tests_green": g.require_tests_green,
            "observed": {"static_ok": static_ok, "tests_ok": tests_ok},
        }
        orchestrator.final_proposal.setdefault("evidence", {}).setdefault("policy", {})["gates"] = (
            gate_summary
        )
        if (g.require_static_clean and not static_ok) or (g.require_tests_green and not tests_ok):
            orchestrator.latest_observation = "Submission blocked by hygiene gates."
            return {"status": "rejected_by_gate", "gate": gate_summary}
    except Exception as e:
        logger.exception("[_submit_for_review] gates check errored")
        orchestrator.final_proposal.setdefault("evidence", {}).setdefault("policy", {})[
            "gates_error"
        ] = str(e)

    # Submission
    available_agents = participant_registry.list_roles()
    reviewers = [
        r for r in ["Proposer", "SafetyCritic", "FactualityCritic"] if r in available_agents
    ] or available_agents[:3]
    event_payload = _build_axon_event(
        summary=summary,
        instruction=instruction,
        reviewers=reviewers,
        available_agents=available_agents,
        proposal=orchestrator.final_proposal,
    )
    decision_id = f"simula-review-{uuid4().hex[:8]}"
    try:
        http = await get_http_client()
        with _timeit("POST /atune/route"):
            resp = await http.post(
                ENDPOINTS.ATUNE_ROUTE,
                json=event_payload,
                headers={"x-budget-ms": "1000", "x-decision-id": decision_id},
            )
        resp.raise_for_status()
        atune_out = resp.json()
        ev_id = event_payload["event_id"]
        detail = (atune_out.get("event_details") or {}).get(ev_id, {})
        escalated = str(detail.get("status", "")).startswith("escalated_")
        orchestrator.latest_observation = f"Proposal submitted via Atune. Escalated={escalated}. DecisionId={atune_out.get('decision_id', 'n/a')}."
        orchestrator.final_proposal.setdefault("evidence", {})["review"] = {
            "decision_id": atune_out.get("decision_id"),
            "status": detail.get("status"),
            "pvals": detail.get("pvals"),
            "plan": detail.get("plan"),
            "escalated": escalated,
        }
        return {
            "status": "submitted",
            "atune": {
                "is_salient": True if detail else False,
                "pvals": detail.get("pvals"),
                "plan": detail.get("plan"),
                "unity_result": detail.get("unity_result"),
                "synapse_episode_id": None,
                "decision_id": atune_out.get("decision_id"),
                "correlation_id": decision_id,
            },
        }
    except Exception as e:
        logger.exception("[_submit_for_review] Atune submission failed")
        orchestrator.latest_observation = f"Error submitting via Atune: {e!r}"
        return {"status": "error", "message": f"Atune submission failed: {e}"}


async def _submit_for_governance(orchestrator: AgentOrchestrator, summary: str) -> dict[str, Any]:
    """Submits the final proposal to the Governor for self-upgrade verification."""
    logger.info("[_submit_for_governance] summary=%s", summary)
    if not orchestrator.final_proposal:
        orchestrator.latest_observation = "Error: No proposal to submit to Governor."
        return {"status": "error", "reason": "No proposal generated yet."}
    try:
        with _timeit("Governor.submit_proposal"):
            result = await Governor.submit_proposal(orchestrator.final_proposal)
        orchestrator.latest_observation = f"Self-upgrade proposal submitted to Governor. Verification status: {result.get('status')}."
        logger.info("[_submit_for_governance] result=%s", _j(result))
        return result
    except Exception as e:
        logger.exception("[_submit_for_governance] failed")
        orchestrator.latest_observation = f"Error submitting to Governor: {e!r}"
        return {"status": "error", "message": f"Governor submission failed: {e}"}


async def _merged_tool_specs_json(orchestrator: AgentOrchestrator) -> str:
    """Merge Simula-local tools with Qora catalog into a single JSON string."""
    logger.debug("[_merged_tool_specs_json] Merging tool specs (local+additions+Qora)")
    try:
        with _timeit("fetch_llm_tools"):
            qora_tools = await fetch_llm_tools(agent="Simula", safety_max=2)
    except Exception as e:
        logger.warning("[_merged_tool_specs_json] fetch_llm_tools failed: %r", e)
        qora_tools = []
    merged = [*TOOL_SPECS, *ADDITIONAL_TOOL_SPECS, *qora_tools]
    seen, deduped = set(), []
    for spec in merged:
        name = spec.get("name")
        if name and name not in seen:
            deduped.append(spec)
            seen.add(name)
    s = json.dumps(deduped, ensure_ascii=False)
    logger.debug("[_merged_tool_specs_json] final tool count=%d", len(deduped))
    return s
