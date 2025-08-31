# systems/unity/core/protocols/meta_criticism.py
from __future__ import annotations

import inspect
import uuid
from typing import Any

from core.llm.bus import event_bus
from core.services.synapse import synapse
from core.utils.neo.cypher_query import cypher_query
from systems.unity.core.neo import graph_writes
from systems.unity.schemas import DeliberationSpec, MetaCriticismProposalEvent, VerdictModel


async def _emit_event(name: str, payload: dict[str, Any]) -> None:
    pub = getattr(event_bus, "publish", None)
    if not pub:
        return
    is_async = inspect.iscoroutinefunction(pub)
    try:
        if is_async:
            await pub(name, payload)
        else:
            pub(name, payload)
    except TypeError:
        merged = {"event": name, **(payload or {})}
        if is_async:
            await pub(merged)
        else:
            pub(merged)


class MetaCriticismProtocol:
    def __init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str):
        self.spec = spec
        self.deliberation_id = deliberation_id
        self.episode_id = episode_id
        self.synapse = synapse
        self.turn = 0

    async def _add_transcript(self, role: str, content: str):
        self.turn += 1
        await graph_writes.record_transcript_chunk(self.deliberation_id, self.turn, role, content)

    async def _fetch_deliberation(self, delib_id: str) -> dict[str, Any]:
        query = """
        MATCH (d:Deliberation {id:$id})
        OPTIONAL MATCH (d)-[:HAS_TRANSCRIPT]->(tc:TranscriptChunk)
        WITH d, tc
        ORDER BY tc.turn ASC
        WITH d, collect({turn: coalesce(tc.turn, 0), role: coalesce(tc.role,''), content: coalesce(tc.content,'')}) AS transcript
        OPTIONAL MATCH (d)-[:RESULTED_IN]->(v:Verdict)
        RETURN transcript,
               coalesce(v.outcome, 'UNKNOWN') AS outcome,
               coalesce(v.confidence, 0.0) AS confidence,
               coalesce(v.uncertainty, 1.0) AS uncertainty
        """
        rows = await cypher_query(query, {"id": delib_id}) or []
        if not rows:
            return {
                "transcript": [],
                "verdict": {"outcome": "UNKNOWN", "confidence": 0.0, "uncertainty": 1.0},
            }
        row = rows[0]
        return {
            "transcript": row.get("transcript") or [],
            "verdict": {
                "outcome": row.get("outcome", "UNKNOWN"),
                "confidence": float(row.get("confidence", 0.0)),
                "uncertainty": float(row.get("uncertainty", 1.0)),
            },
        }

    @staticmethod
    def _measure_efficiency(
        transcript: list[dict[str, Any]],
        verdict: dict[str, Any],
    ) -> dict[str, Any]:
        effective_turns = [
            t
            for t in transcript
            if not (t.get("turn", 0) == 1 and str(t.get("role", "")).lower() == "orchestrator")
        ]
        total_rounds = max(0, len(effective_turns))
        final_conf = float(verdict.get("confidence", 0.0))
        final_unc = float(verdict.get("uncertainty", 1.0))
        CONF_OK, UNC_OK, BASE_CAP = 0.90, 0.20, 5
        early_stop_triggered = (final_conf >= CONF_OK) or (final_unc <= UNC_OK)
        suggested_max_rounds = (
            BASE_CAP if early_stop_triggered else max(BASE_CAP + 2, min(12, total_rounds))
        )
        return {
            "total_rounds": total_rounds,
            "final_confidence": final_conf,
            "final_uncertainty": final_unc,
            "early_stop_triggered": early_stop_triggered,
            "suggested_max_rounds": suggested_max_rounds,
        }

    def _build_proposal(
        self,
        source_delib_id: str,
        diag: dict[str, Any],
    ) -> MetaCriticismProposalEvent:
        goal = (
            "Introduce early stopping + dynamic round capping for debate protocols: "
            f"set max_rounds ≤ {diag['suggested_max_rounds']} when confidence ≥ 0.90 or uncertainty ≤ 0.20; otherwise continue adaptively."
        )
        evidence = {
            "observed_rounds": int(diag["total_rounds"]),
            "final_confidence": float(diag["final_confidence"]),
            "final_uncertainty": float(diag["final_uncertainty"]),
            "early_stop_would_apply": bool(diag["early_stop_triggered"]),
            "suggested_max_rounds": int(diag["suggested_max_rounds"]),
        }
        return MetaCriticismProposalEvent(
            proposal_id=f"mcp_{uuid.uuid4().hex}",
            source_deliberation_id=source_delib_id,
            proposed_task_goal=goal,
            evidence=evidence,
            notes="Derived from transcript and verdict statistics; reduces redundant rounds while keeping safety margins.",
        )

    async def run(self) -> dict[str, Any]:
        await self._add_transcript("Orchestrator", "Starting Meta-Criticism protocol.")
        source_delib_id = self.spec.inputs[0].value if getattr(self.spec, "inputs", None) else None
        if not source_delib_id:
            verdict = VerdictModel(
                outcome="REJECT",
                confidence=1.0,
                uncertainty=0.0,
                dissent="No source deliberation ID provided.",
            )
            return {"verdict": verdict, "artifact_ids": {}}

        await self._add_transcript(
            "MetaCritic",
            f"Analyzing deliberation trace for '{source_delib_id}'.",
        )
        data = await self._fetch_deliberation(source_delib_id)
        transcript, verdict_meta = data["transcript"], data["verdict"]
        if not transcript or verdict_meta["outcome"] == "UNKNOWN":
            await self._add_transcript(
                "MetaCritic",
                "Source deliberation not found or missing verdict.",
            )
            verdict = VerdictModel(
                outcome="REJECT",
                confidence=0.9,
                uncertainty=0.1,
                dissent="Missing artifacts prevent analysis.",
            )
            return {"verdict": verdict, "artifact_ids": {}}

        diag = self._measure_efficiency(transcript, verdict_meta)
        if diag["early_stop_triggered"] or diag["total_rounds"] > diag["suggested_max_rounds"]:
            await self._add_transcript(
                "MetaCritic",
                f"Inefficiency detected; proposing early-stop + max_rounds≤{diag['suggested_max_rounds']}.",
            )
            proposal = self._build_proposal(source_delib_id, diag)
            # Persist proposal as artifact for traceability
            pid = await graph_writes.create_artifact(
                self.deliberation_id,
                "metacriticism_proposal",
                proposal.model_dump(),
            )
            await _emit_event(
                "unity.metacriticism.proposal.created",
                {"proposal": proposal.model_dump(), "artifact_id": pid},
            )
            await self._add_transcript(
                "MetaCritic",
                f"Published proposal '{proposal.proposal_id}' to event bus.",
            )
            verdict = VerdictModel(
                outcome="APPROVE",
                confidence=0.95,
                uncertainty=0.05,
                dissent="Improvement proposal emitted.",
            )
            return {"verdict": verdict, "artifact_ids": {"metacriticism_proposal": pid}}

        await self._add_transcript(
            "MetaCritic",
            "No material inefficiency detected under current thresholds.",
        )
        verdict = VerdictModel(
            outcome="NO_ACTION",
            confidence=0.98,
            uncertainty=0.02,
            dissent="Deliberation appears efficient.",
        )
        return {"verdict": verdict, "artifact_ids": {}}
