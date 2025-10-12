# systems/unity/core/room/orchestrator.py
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid
from typing import Any

from core.llm.bus import event_bus
from core.services.synapse import synapse

# --- FIX: Import the event schema for the final publication step ---
from systems.equor.schemas import DeliberationConclusion, UnityDeliberationCompleteEvent
from systems.synapse.core import snapshots as rcu_snapshotter
from systems.synapse.core.registry import arm_registry
from systems.synapse.schemas import Candidate, TaskContext
from systems.unity.core.neo import graph_writes
from systems.unity.core.policy.safety_policy import violates as safety_violates
from systems.unity.core.protocols.aletheia_protocol import AletheiaOrchestrator
from systems.unity.schemas import BroadcastEvent, DeliberationSpec, VerdictModel

log = logging.getLogger(__name__)


async def _await_maybe(obj):
    return await obj if inspect.isawaitable(obj) else obj


async def _safety_check(spec: DeliberationSpec) -> tuple[bool, str | None, str]:
    try:
        res = await _await_maybe(safety_violates(spec))
    except Exception as e:
        log.warning("[Unity] Safety check failed open (treating as NOT violated): %s", e)
        return False, None, ""
    if isinstance(res, tuple):
        if len(res) >= 3:
            return bool(res[0]), res[1], res[2] or ""
        if len(res) == 2:
            return bool(res[0]), res[1], ""
        if len(res) == 1:
            return bool(res[0]), None, ""
    if isinstance(res, bool):
        return res, None, ""
    log.warning("[Unity] Unexpected safety_violates return type: %r", type(res))
    return False, None, ""


def _as_dict(obj: Any) -> dict[str, Any]:
    try:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return json.loads(json.dumps(obj, default=lambda o: getattr(o, "__dict__", str(o))))
    except Exception:
        return {"raw": str(obj)}


def _risk_level_from_urgency(u: str | None) -> str:
    m = {"low": "low", "normal": "medium", "high": "high"}
    return m.get((u or "").strip().lower(), "medium")


class DeliberationManager:
    _instance: DeliberationManager | None = None
    _inited: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self.__class__._inited:
            return
        sub = event_bus.subscribe("unity.workspace.ignition", self._on_workspace_ignition)
        if inspect.isawaitable(sub):
            asyncio.create_task(sub)
        self.__class__._inited = True

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

    from core.telemetry.decorators import episode

    @episode("unity.orchestrator")
    async def run_session(self, spec: DeliberationSpec) -> dict[str, Any]:
        spec.episode_id = spec.episode_id or f"ep_{uuid.uuid4().hex}"
        rcu_start_ref = str(rcu_snapshotter.stamp())

        deliberation_id = await graph_writes.create_deliberation_node(
            spec.episode_id,
            spec,
            rcu_start_ref,
        )

        # Initial safety check on the input spec
        violates, rule_id, excerpt = await _safety_check(spec)
        if violates:
            log.warning("[Unity] Deliberation spec vetoed by safety policy. Rule ID: %s", rule_id)
            verdict = VerdictModel(
                outcome="REJECT",
                confidence=1.0,
                uncertainty=0.0,
                dissent=f"Spec violates safety policy '{rule_id}'. Content: {excerpt}",
            )
            # Short-circuit and finalize with a rejection verdict
            rcu_end_ref = str(rcu_snapshotter.stamp())
            verdict_id = await graph_writes.finalize_verdict(deliberation_id, verdict, rcu_end_ref)
            return {
                "episode_id": spec.episode_id,
                "deliberation_id": deliberation_id,
                "verdict": verdict,
                "artifact_ids": {"verdict": verdict_id},
            }

        protocol_id = "Aletheia_v1"
        selected_arm_id = "core:Aletheia"
        risk_level = _risk_level_from_urgency(getattr(spec, "urgency", None))

        try:
            log.info("[Unity] Querying Synapse to select the optimal protocol...")
            task_ctx = TaskContext(
                task_key=f"unity.{spec.goal}",
                goal=f"Select protocol for deliberation: {spec.topic}",
                risk_level=risk_level,
                budget="normal",
                mode_hint="unity",
                context={"topic_length": len(spec.topic)},
            )
            unity_arms = arm_registry.get_arms_for_mode("unity")
            if not unity_arms:
                raise ValueError("No 'unity' mode arms are registered. Cannot select a protocol.")
            candidates = [Candidate(id=arm.id, content={}) for arm in unity_arms]
            selection = await synapse.select_arm(task_ctx=task_ctx, candidates=candidates)
            selected_arm_id = selection.champion_arm.arm_id
            champion_content = selection.champion_arm.content
            if champion_content:
                protocol_id = champion_content.get("protocol_id", protocol_id)
            log.info(
                "[Unity] Synapse selected arm '%s' (protocol: %s) for deliberation.",
                selected_arm_id,
                protocol_id,
            )
        except Exception as e:
            log.warning(
                "[Unity] Synapse arm selection failed, using fallback 'core:Aletheia'. Reason: %s",
                e,
            )

        await graph_writes.annotate_deliberation(
            deliberation_id,
            protocol_id=protocol_id,
            selected_arm_id=selected_arm_id,
            risk_level=risk_level,
        )

        runner = AletheiaOrchestrator(spec, deliberation_id, spec.episode_id)
        result = await runner.run()

        verdict: VerdictModel = result["verdict"]
        proto_artifacts: dict[str, str] = dict(result.get("artifact_ids") or {})
        rcu_end_ref = str(rcu_snapshotter.stamp())
        verdict_id = await graph_writes.finalize_verdict(deliberation_id, verdict, rcu_end_ref)
        artifact_ids = {"verdict": verdict_id, **proto_artifacts}

        # --- FIX: ADD THE EVENT PUBLICATION LOGIC ---
        # After the deliberation is complete and the verdict is finalized,
        # publish the event for downstream systems like Equor.
        if verdict.outcome == "APPROVE" or verdict.confidence > 0.75:
            try:
                conclusion = DeliberationConclusion(
                    text=verdict.dissent or "No detailed reasoning provided.",
                    confidence=verdict.confidence,
                    agreement_level=1.0
                    - verdict.uncertainty,  # Use uncertainty as a proxy for agreement
                )
                # This assumes 'spec.inputs' contains a reference to the triggering Atune event
                trigger_ref = next((inp for inp in spec.inputs if inp.kind == "graph_ref"), None)

                event_payload = UnityDeliberationCompleteEvent(
                    deliberation_episode_id=spec.episode_id,
                    triggering_event_id=spec.triggering_event_id or "unknown",
                    triggering_source="EcodiaOS.Atune",  # Assuming Atune is the source
                    topic=spec.topic,
                    participating_agents=["AletheiaProtocol"],  # Or a more detailed list
                    conclusion=conclusion,
                )

                # Publish to the event bus for Equor's IdentityEvolver to consume
                await event_bus.publish("unity.deliberation.complete", event_payload.model_dump())
                log.info(
                    "[Unity] Published UnityDeliberationCompleteEvent for episode '%s'.",
                    spec.episode_id,
                )

            except Exception as e:
                log.error("[Unity] Failed to publish deliberation completion event: %s", e)

        # Log outcome to Synapse for meta-learning
        try:
            final_metrics = {
                "chosen_arm_id": selected_arm_id,
                "utility": 0.5,
                "latency_ms": getattr(runner, "turn", 0) * 1000,
                "protocol_id": protocol_id,
                "risk_level": risk_level,
                "verdict": _as_dict(verdict),
                "artifact_ids": artifact_ids,
                "features": {
                    "topic": spec.topic,
                    "inputs_len": len(spec.inputs or []),
                    "constraints_len": len(spec.constraints or []),
                },
            }
            await synapse.log_outcome(
                episode_id=spec.episode_id,
                task_key=f"unity.{spec.goal or 'deliberation'}",
                metrics=final_metrics,
            )
        except Exception as e:
            log.warning("[Unity->Synapse] failed to log outcome: %s", e)

        return {
            "episode_id": spec.episode_id,
            "deliberation_id": deliberation_id,
            "verdict": verdict,
            "artifact_ids": artifact_ids,
        }
