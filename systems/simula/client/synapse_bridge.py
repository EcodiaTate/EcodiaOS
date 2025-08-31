# systems/simula/integrations/synapse_bridge.py
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.services.synapse import SynapseClient
from systems.synapse.schemas import Candidate, TaskContext


# Optional: centralize correlation headers here if you need to reuse them later
def new_decision_id() -> str:
    return f"dec_{uuid.uuid4().hex[:12]}"


@dataclass
class Metrics:
    latency_ms: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class SynapseSession:
    task_key: str
    goal: str
    risk_level: str = "medium"
    budget: str = "normal"
    decision_id: str | None = None
    features: dict[str, Any] = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)

    # runtime
    episode_id: str | None = None
    chosen_arm_id: str | None = None
    model_params: dict[str, Any] = field(default_factory=dict)
    started_at_ns: int | None = None
    metrics: Metrics = field(default_factory=Metrics)

    def _ctx(self) -> TaskContext:
        # TaskContext is your existing pydantic Schema
        return TaskContext(
            task_key=self.task_key,
            goal=self.goal,
            risk_level=self.risk_level,
            budget=self.budget,
        )

    from core.telemetry.decorators import episode

    @episode("simula.synapse_bridge")
    async def start(self, synapse: SynapseClient) -> None:
        self.started_at_ns = time.time_ns()
        sel = await synapse.select_arm(self._ctx(), self.candidates)
        self.episode_id = sel.episode_id
        self.chosen_arm_id = sel.champion_arm.arm_id
        self.model_params = await synapse.arm_inference_config(self.chosen_arm_id or "")
        # Pre-seed features for outcome (helps joinability in learning)
        self.features.setdefault("decision_id", self.decision_id or new_decision_id())
        self.features.setdefault("simula_model", self.model_params.get("model"))
        self.features.setdefault("simula_temperature", self.model_params.get("temperature"))
        self.features.setdefault("simula_max_tokens", self.model_params.get("max_tokens"))

    def add_tool_call(
        self,
        ok: bool,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        **extra,
    ):
        self.metrics.tool_calls += 1
        if not ok:
            self.metrics.tool_errors += 1
        self.metrics.tokens_in += int(tokens_in or 0)
        self.metrics.tokens_out += int(tokens_out or 0)
        self.metrics.cost_usd += float(cost_usd or 0.0)
        if extra:
            self.metrics.extras.update(extra)
            print(
                f"[SynapseSession] tool_call ok={ok} tokens_in={tokens_in} tokens_out={tokens_out} cost_usd={cost_usd}",
            )

    async def finish(
        self,
        synapse: SynapseClient,
        *,
        utility: float,
        verdict: dict[str, Any] | None = None,
        artifact_ids: list[str] | None = None,
        extra_metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Finalize the episode and log outcome metrics to Synapse.

        NOTE: SynapseClient.log_outcome(...) takes (episode_id, task_key, metrics, simulator_prediction)
        — it does NOT accept an 'outcome' kwarg. We include 'verdict' and 'artifact_ids' inside metrics.
        """
        if self.started_at_ns:
            self.metrics.latency_ms = int((time.time_ns() - self.started_at_ns) / 1_000_000)

        # Build metrics payload (flat/primitives-friendly). Keep rich objects in JSON-friendly fields.
        metrics_payload: dict[str, Any] = {
            "chosen_arm_id": self.chosen_arm_id,
            "utility": float(utility),
            "latency_ms": int(self.metrics.latency_ms),
            "tool_calls": int(self.metrics.tool_calls),
            "tool_errors": int(self.metrics.tool_errors),
            "tokens_in": int(self.metrics.tokens_in),
            "tokens_out": int(self.metrics.tokens_out),
            "cost_usd": float(self.metrics.cost_usd),
            "features": dict(self.features),
        }

        # Fold optional details into metrics to preserve them without breaking the API
        if verdict is not None:
            metrics_payload["verdict"] = verdict
        if artifact_ids is not None:
            metrics_payload["artifact_ids"] = list(artifact_ids)
        if self.metrics.extras:
            metrics_payload["extras"] = dict(self.metrics.extras)
        if extra_metrics:
            metrics_payload.update(extra_metrics)
        import json
        import logging

        logger = logging.getLogger("systems.simula.synapse_bridge")
        logger.info("[SynapseSession] METRICS=%s", json.dumps(metrics_payload, ensure_ascii=False))

        # Call with the correct signature (no 'outcome' kwarg)
        return await synapse.log_outcome(
            episode_id=self.episode_id or f"syn_{uuid.uuid4().hex}",
            task_key=self.task_key,
            metrics=metrics_payload,
            simulator_prediction=None,
        )

    # Optional pairwise preference (A/B) helper
    async def log_preference(
        self,
        synapse: SynapseClient,
        *,
        a_ep: str,
        b_ep: str,
        winner: str,
        notes: str = "",
    ) -> dict[str, Any]:
        payload = {
            "task_key": self.task_key,
            "a_episode_id": a_ep,
            "b_episode_id": b_ep,
            "A": {"arm_id": "A"},
            "B": {"arm_id": "B"},
            "winner": winner,
            "notes": notes,
        }
        return await synapse.ingest_preference(payload)
