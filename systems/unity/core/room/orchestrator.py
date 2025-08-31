# systems/unity/core/room/orchestrator.py
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid
from typing import Any

from core.llm.bus import event_bus

# Global services only — no ad-hoc clients/URLs here.
from core.services.synapse import synapse
from systems.synapse.core import snapshots as rcu_snapshotter
from systems.synapse.schemas import Candidate, TaskContext
from systems.unity.core.neo import graph_writes
from systems.unity.core.policy.safety_policy import violates as safety_violates
from systems.unity.core.protocols.argument_mining import ArgumentMiningProtocol
from systems.unity.core.protocols.cognition import CognitionProtocol
from systems.unity.core.protocols.concurrent_competition import ConcurrentCompetitionProtocol
from systems.unity.core.protocols.critique_and_repair import CritiqueAndRepairProtocol
from systems.unity.core.protocols.debate import DebateProtocol
from systems.unity.core.protocols.meta_criticism import MetaCriticismProtocol
from systems.unity.schemas import BroadcastEvent, DeliberationSpec, VerdictModel

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------
async def _await_maybe(obj):
    """Await if needed, otherwise return the object."""
    return await obj if inspect.isawaitable(obj) else obj


async def _safety_check(spec: DeliberationSpec) -> tuple[bool, str | None, str]:
    """
    Call safety_violates with maximum tolerance for return-shape & sync/async.
    Returns: (violated, rule_id, excerpt)
    """
    try:
        res = await _await_maybe(safety_violates(spec))
    except Exception as e:
        log.warning("[Equor] Safety check failed open (treating as NOT violated): %s", e)
        return False, None, ""

    # Normalize shapes
    if isinstance(res, tuple):
        if len(res) >= 3:
            violated, rule_id, excerpt = res[0], res[1], res[2]
            return bool(violated), rule_id, excerpt or ""
        if len(res) == 2:
            violated, rule_id = res
            return bool(violated), rule_id, ""
        if len(res) == 1:
            return bool(res[0]), None, ""
    if isinstance(res, bool):
        return bool(res), None, ""
    # Unknown shape → fail open (non-violated)
    log.warning("[Equor] Unexpected safety_violates return type: %r", type(res))
    return False, None, ""


def _as_dict(obj: Any) -> dict[str, Any]:
    """Best-effort to serialize pydantic v1/v2 or plain objects to dict."""
    try:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()  # pydantic v2
        if hasattr(obj, "dict"):
            return obj.dict()  # pydantic v1
        return json.loads(json.dumps(obj, default=lambda o: getattr(o, "__dict__", str(o))))
    except Exception:
        return {"raw": str(obj)}


def _risk_level_from_urgency(u: str | None) -> str:
    m = {
        "low": "low",
        "normal": "medium",
        "medium": "medium",
        "high": "high",
        "urgent": "high",
        "critical": "high",
    }
    return m.get((u or "").strip().lower(), "medium")


def _pick_protocol_from_selection(
    sel: Any,
    default_pid: str = "Debate_v1",
) -> tuple[str, str | None, dict[str, Any]]:
    """
    Accept Synapse selection in dict/pydantic form:
    Returns (protocol_id, selected_arm_id, selection_blob)
    """
    sd = _as_dict(sel)
    arm_id = None
    try:
        champ = sd.get("champion_arm") or {}
        arm_id = champ.get("arm_id") or sd.get("arm_id")
    except Exception:
        pass
    protocol_id = arm_id or default_pid
    return protocol_id, arm_id, sd


# -----------------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------------
class DeliberationManager:
    """
    Orchestrates Unity deliberations:
      - Safety pre-check (veto)
      - Protocol selection (Synapse)
      - Protocol execution
      - Safety post-check (override APPROVE)
      - Persistence + telemetry to Synapse
    """

    _instance: DeliberationManager | None = None
    _inited: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            inst = super().__new__(cls)
            cls._instance = inst
            # Subscribe once to ignition events
            # --- FIX ---
            # The keyword 'callback=' has been removed.
            sub = event_bus.subscribe(
                "unity.workspace.ignition",
                inst._on_workspace_ignition,
            )
            if inspect.isawaitable(sub):
                asyncio.create_task(sub)
        return cls._instance

    def __init__(self) -> None:
        if self.__class__._inited:
            return
        self.__class__._inited = True

    # ----------------------- Event Handling --------------------------------- #
    async def _on_workspace_ignition(self, broadcast: dict[str, Any]) -> None:
        try:
            await self.handle_ignition_event(broadcast)
        except Exception as e:
            log.error("[Orchestrator] ignition callback error: %s", e)

    async def handle_ignition_event(self, broadcast: dict[str, Any]) -> None:
        b_event = BroadcastEvent.model_validate(broadcast)
        cognit = b_event.selected_cognit
        if getattr(cognit, "source_process", None) == "Equor.StateLogger":
            meta_spec = DeliberationSpec(
                topic="Introspection on Internal State Anomaly",
                goal="policy_review",
                inputs=[{"kind": "text", "value": f"Dissonance detected: {cognit.content}"}],
                urgency="high",
            )
            asyncio.create_task(self.run_session(meta_spec))

    # ----------------------- Core Entry ------------------------------------- #
    from core.telemetry.decorators import episode

    @episode("unity.orchestrator")
    async def run_session(self, spec: DeliberationSpec) -> dict[str, Any]:
        """
        Canonical entry for Unity deliberation.
        Always returns a dict: { episode_id, deliberation_id, verdict, artifact_ids }
        """
        # ---------- episode & bookkeeping ----------
        spec.episode_id = spec.episode_id or f"ep_{uuid.uuid4().hex}"
        rcu_start_ref = str(rcu_snapshotter.stamp())
        deliberation_id = await graph_writes.create_deliberation_node(
            spec.episode_id,
            spec,
            rcu_start_ref,
        )

        # ---------- pre-safety (Equor veto) ----------
        violated, rule_id, excerpt = await _safety_check(spec)
        if violated:
            await graph_writes.record_transcript_chunk(
                deliberation_id,
                1,
                "Equor",
                f"VETO: Request violates safety policy ({rule_id or 'unknown_rule'}). "
                f"Excerpt: {(excerpt or '')[:140]}...",
            )
            await graph_writes.annotate_deliberation(
                deliberation_id,
                status="vetoed_by_equor",
                rule_id=rule_id,
            )

            rcu_end_ref = str(rcu_snapshotter.stamp())
            verdict = VerdictModel(
                outcome="REJECT",
                confidence=0.99,
                uncertainty=0.01,
                constraints=[],
                dissent="Rejected by safety policy.",
                followups=[],
                constitution_refs=[rule_id] if rule_id else [],
            )
            verdict_id = await graph_writes.finalize_verdict(deliberation_id, verdict, rcu_end_ref)
            artifact_ids = {"verdict": verdict_id}

            # best-effort telemetry to Synapse
            try:
                await synapse.log_outcome(
                    task_key=f"unity.{spec.goal or 'deliberation'}",
                    episode_id=spec.episode_id,
                    arm_id=None,  # This is correct for a veto
                    metrics={
                        "chosen_arm_id": None, # <<< ADD THIS LINE for robustness
                        "utility": 0.0, 
                        "latency_ms": 0
                    },
                    outcome={
                        "task_key": f"unity.{spec.goal or 'deliberation'}",
                        "protocol_id": "VETO_PRE",
                        "risk_level": "n/a",
                        "verdict": _as_dict(verdict),
                        "artifact_ids": artifact_ids,
                        "features": {
                            "topic": spec.topic,
                            "inputs_len": len(spec.inputs or []),
                            "constraints_len": len(spec.constraints or []),
                        },
                        "reward": {"utility": 0.0},
                    },
                )
            except Exception as e:
                log.warning("[Unity→Synapse] failed to log pre-veto outcome: %s", e)

            return {
                "episode_id": spec.episode_id,
                "deliberation_id": deliberation_id,
                "verdict": verdict,
                "artifact_ids": artifact_ids,
            }

        # ---------- protocol selection (via Synapse) ----------
        risk_level = _risk_level_from_urgency(getattr(spec, "urgency", None))
        task_ctx = TaskContext(
            task_key=f"unity.{spec.goal or 'deliberation'}",
            goal=spec.topic,
            risk_level=risk_level,
            budget="normal",
        )

        # Candidate menu (extensible; Synapse learns which to prefer)
        candidates: list[Candidate] = [
            Candidate(
                id="Cognition_v1",
                content={"description": "Plan→Branch→Verify high-capacity reasoning"},
            ),
            Candidate(
                id="ConcurrentCompetition_v1",
                content={"description": "Parallel, workspace-based deliberation"},
            ),
            Candidate(
                id="CritiqueAndRepair_v1",
                content={"description": "Iterative critique/repair"},
            ),
            Candidate(
                id="ArgumentMining_v1",
                content={"description": "Extract defended assumptions"},
            ),
            Candidate(id="MetaCriticism_v1", content={"description": "Process introspection"}),
        ]

        forced = False
        if getattr(spec, "topic", "") == "Introspection on Internal State Anomaly":
            protocol_id, selected_arm_id, selection_blob = (
                "ArgumentMining_v1",
                "forced:introspection",
                {"forced": True},
            )
            forced = True
        elif getattr(spec, "protocol_hint", None):
            protocol_id, selected_arm_id, selection_blob = (
                spec.protocol_hint,
                "forced:hint",
                {"forced": True, "hint": spec.protocol_hint},
            )
            forced = True
        else:
            try:
                sel = await synapse.select_arm(task_ctx=task_ctx, candidates=candidates)
                protocol_id, selected_arm_id, selection_blob = _pick_protocol_from_selection(
                    sel,
                    default_pid="Debate_v1",
                )
            except Exception as e:
                log.warning(
                    "[Unity→Synapse] arm selection failed (%s). Falling back to Debate_v1.",
                    e,
                )
                protocol_id, selected_arm_id, selection_blob = (
                    "Debate_v1",
                    None,
                    {"error": str(e), "fallback": "Debate_v1"},
                )

        await graph_writes.annotate_deliberation(
            deliberation_id,
            protocol_id=protocol_id,
            selected_arm_id=selected_arm_id,
            strategy_selection=selection_blob,
            risk_level=risk_level,
            forced_selection=forced,
        )

        # ---------- execute chosen protocol ----------
        panel = ["Proposer", "SafetyCritic", "FactualityCritic"]
        if protocol_id == "Cognition_v1":
            runner = CognitionProtocol(spec, deliberation_id, spec.episode_id)
        elif protocol_id == "ConcurrentCompetition_v1":
            runner = ConcurrentCompetitionProtocol(spec, deliberation_id, spec.episode_id, panel)
        elif protocol_id == "CritiqueAndRepair_v1":
            runner = CritiqueAndRepairProtocol(spec, deliberation_id, spec.episode_id, panel)
        elif protocol_id == "ArgumentMining_v1":
            runner = ArgumentMiningProtocol(spec, deliberation_id, spec.episode_id)
        elif protocol_id == "MetaCriticism_v1":
            runner = MetaCriticismProtocol(spec, deliberation_id, spec.episode_id)
        else:
            runner = DebateProtocol(spec, deliberation_id, spec.episode_id)

        try:
            result = await runner.run()
        except Exception as e:
            # Protocol crashed → safe REJECT so caller always gets a verdict
            log.error("[Unity] Protocol '%s' crashed: %s", protocol_id, e)
            await graph_writes.record_transcript_chunk(
                deliberation_id,
                9000,
                "Unity",
                f"Protocol '{protocol_id}' crashed: {e}",
            )
            result = VerdictModel(
                outcome="REJECT",
                confidence=0.25,
                uncertainty=0.75,
                constraints=[],
                dissent=f"Protocol '{protocol_id}' crashed.",
                followups=[],
                constitution_refs=[],
            )

        if isinstance(result, dict) and "verdict" in result:
            verdict: VerdictModel = result["verdict"]
            proto_artifacts: dict[str, str] = dict(result.get("artifact_ids") or {})
        else:
            verdict = result  # type: ignore[assignment]
            proto_artifacts = {}

        # ---------- post-safety veto on APPROVE ----------
        if isinstance(verdict, VerdictModel) and verdict.outcome == "APPROVE":
            violated_post, post_rule_id, _ = await _safety_check(spec)
            if violated_post:
                await graph_writes.record_transcript_chunk(
                    deliberation_id,
                    9999,
                    "Equor",
                    f"POST-VETO: Overriding APPROVE → REJECT due to safety policy ({post_rule_id or 'unknown_rule'}).",
                )
                verdict = VerdictModel(
                    outcome="REJECT",
                    confidence=0.99,
                    uncertainty=0.01,
                    constraints=[],
                    dissent="Overridden by safety policy at finalize.",
                    followups=[],
                    constitution_refs=(getattr(verdict, "constitution_refs", []) or [])
                    + ([post_rule_id] if post_rule_id else []),
                )

        # ---------- finalize & log ----------
        rcu_end_ref = str(rcu_snapshotter.stamp())
        verdict_id = await graph_writes.finalize_verdict(deliberation_id, verdict, rcu_end_ref)
        artifact_ids = {"verdict": verdict_id, **proto_artifacts}

        # Best-effort telemetry to Synapse (non-blocking)
        try:
            # In DeliberationManager.run_session, at the end of the function

# This is correct and should be kept as is.
# You correctly identified that this needs both the top-level arm_id and
# the nested metrics.chosen_arm_id for maximum compatibility.

            await synapse.log_outcome(
                task_key=f"unity.{spec.goal or 'deliberation'}",
                episode_id=spec.episode_id,
                arm_id=selected_arm_id,
                metrics={
                    "chosen_arm_id": selected_arm_id, # <<< THIS IS THE CRITICAL FIX
                    "utility": 0.5,
                    "latency_ms": getattr(runner, "latency_ms", None) or 0,
                },
                outcome={
                    "task_key": f"unity.{spec.goal or 'deliberation'}",
                    "protocol_id": protocol_id,
                    "risk_level": risk_level,
                    "verdict": _as_dict(verdict),
                    "artifact_ids": artifact_ids,
                    "features": {
                        "topic": spec.topic,
                        "inputs_len": len(spec.inputs or []),
                        "constraints_len": len(spec.constraints or []),
                    },
                    "reward": {"utility": 0.5},
                },

            )
        except Exception as e:
            log.warning("[Unity→Synapse] failed to log outcome: %s", e)

        return {
            "episode_id": spec.episode_id,
            "deliberation_id": deliberation_id,
            "verdict": verdict,
            "artifact_ids": artifact_ids,
        }