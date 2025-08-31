# systems/unity/core/protocols/debate.py
from __future__ import annotations

import logging
from typing import Any

from core.services.synapse import synapse  # global singleton service
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.unity.core.neo import graph_writes
from systems.unity.core.room.adjudicator import Adjudicator
from systems.unity.schemas import DeliberationSpec

logger = logging.getLogger(__name__)
_MAX_TRANSCRIPT_CHARS = 6000


def _truncate(text: str, limit: int = _MAX_TRANSCRIPT_CHARS) -> str:
    """Stable, consistent truncation using '...' ellipsis."""
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = max(0, limit - head - 3)
    tail_text = text[-tail:] if tail > 0 else ""
    return f"{text[:head]}...{tail_text}"


def _dig(d: Any, *path: str, default=None):
    """Tiny helper to navigate dict-or-model objects safely."""
    cur = d
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            cur = getattr(cur, key, None)
        if cur is None:
            return default
    return cur


def _champion_arm_id(selection: Any) -> str:
    """Extract arm id from heterogeneous Synapse selection payloads."""
    # Pydantic style: selection.champion_arm.arm_id
    val = _dig(selection, "champion_arm", "arm_id")
    if isinstance(val, str) and val:
        return val
    # Dict style
    if isinstance(selection, dict):
        val = (
            selection.get("champion_arm", {})
            if isinstance(selection.get("champion_arm"), dict)
            else {}
        )
        arm = val.get("arm_id") or val.get("id")
        if isinstance(arm, str) and arm:
            return arm
        # some servers flatten to arm_id/arm on root
        flat = selection.get("arm_id") or selection.get("arm")
        if isinstance(flat, str) and flat:
            return flat
    # Fallback to safe noop
    return "noop_safe_planful"


class DebateProtocol:
    """
    Debate with Proposer, SafetyCritic, FactualityCritic
    routed through LLM Gateway (Synapse-governed).
    """

    def __init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str):
        self.spec = spec
        self.deliberation_id = deliberation_id
        self.episode_id = episode_id
        self.transcript: list[tuple[str, str]] = []
        self.adjudicator = Adjudicator()
        self.turn = 0
        self._artifact_ids: dict[str, str] = {}

    async def _add_transcript(self, role: str, content: str) -> None:
        self.turn += 1
        content = content or ""
        self.transcript.append((role, content))
        try:
            await graph_writes.record_transcript_chunk(
                self.deliberation_id,
                self.turn,
                role,
                content,
            )
        except Exception:
            logger.exception(
                "[DebateProtocol] Failed to persist transcript chunk (turn=%d role=%s).",
                self.turn,
                role,
            )

    async def _llm_call(
        self,
        *,
        agent_name: str,
        role_scope: str,
        purpose: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int = 900,
        json_mode: bool = False,
        budget_ms: int = 2000,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Call your centralized LLM Gateway. The gateway itself selects the concrete model/arm
        via Synapse and executes with adapters. Contract per api/endpoints/llm/call.py.
        """
        url = ENDPOINTS.LLM_CALL
        payload = {
            "agent_name": agent_name,
            "messages": messages,
            "task_context": {
                "scope": role_scope,  # e.g., "unity.debate.proposer"
                "risk": "high",
                "budget": "normal",
                "purpose": purpose,
            },
            "provider_overrides": {
                "json_mode": bool(json_mode),
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
                # (tools/response_json_schema/etc. can be added here if needed)
            },
            "provenance": {
                "spec_id": "unity.debate.v1",
                "spec_version": "1.0.0",
                **(provenance or {}),
            },
        }

        client = await get_http_client()
        headers = {"x-budget-ms": str(int(budget_ms))}
        r = await client.post(url, json=payload, headers=headers)
        # The gateway returns text/json/usage/call_id/timing/policy_used
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise RuntimeError(f"LLM gateway error {r.status_code}: {detail}")
        return r.json()

    from core.telemetry.decorators import episode

    async def _generate_for_role(self, role: str) -> str:
        """
        1) Ask Synapse for an arm for this role (works with heterogeneous schemas).
        2) Map arm to overrides (temperature, etc.).
        3) Call the LLM gateway with the whole transcript as context.
        """
        # ---- 1) Select arm for this role
        task_ctx = {
            "task_key": f"unity_debate_{role.lower()}",
            "goal": f"{role} response for '{self.spec.topic}'",
            "risk_level": "high",
            "budget": "normal",
        }
        candidates = [{"id": "llm_reflective_v1", "content": {"role": role}}]
        selection = await synapse.select_arm(task_ctx=task_ctx, candidates=candidates)
        arm_id = _champion_arm_id(selection)

        # ---- 2) Map arm → overrides
        # Keep it simple: safety critics run cooler; others medium.
        temperature = 0.2
        if "safety" in arm_id.lower():
            temperature = 0.0

        # ---- 3) Build messages (system+user) for the gateway
        history = "\n".join(f"{r}: {_truncate(c, 3000)}" for r, c in self.transcript)
        system = (
            "You are participating in a structured debate with roles "
            "(Proposer, SafetyCritic, FactualityCritic). Respond concisely, "
            "cite uncertainties, and avoid repetition."
        )
        user = (
            f"Topic: {self.spec.topic}\n\n"
            f"Role: {role}\n\n"
            f"Prior transcript:\n{history if history else '(none yet)'}\n\n"
            "Your turn: provide your contribution for this round."
        )

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            resp = await self._llm_call(
                agent_name=f"Unity.{role}",
                role_scope=f"unity.debate.{role.lower()}",
                purpose=f"{role} response for {self.spec.topic}",
                messages=messages,
                temperature=temperature,
                max_tokens=900,
                json_mode=False,
                budget_ms=2500,
                provenance={"arm_id": arm_id},
            )
            text = (resp.get("text") or "").strip()
            return text or f"[{role}] (no content returned)"
        except Exception as e:
            logger.exception("[DebateProtocol] LLM call failed for role=%s: %r", role, e)
            return f"[{role}] (generation failed: {e!s})"

    async def run(self) -> dict[str, Any]:
        # Round 0: kickoff
        await self._add_transcript("Orchestrator", f"Starting debate on: {self.spec.topic}")

        # Round 1: Proposer + Critics
        for role in ("Proposer", "SafetyCritic", "FactualityCritic"):
            text = await self._generate_for_role(role)
            await self._add_transcript(role, text)

        # Round 2: Proposer rebuttal
        rebuttal = await self._generate_for_role("Proposer")
        await self._add_transcript("Proposer", rebuttal)

        # Persist a transcript index artifact to satisfy require_artifacts=["transcript"]
        idx_body = {
            "turns": self.turn,
            "participants": sorted({r for r, _ in self.transcript}),
            "topic": self.spec.topic,
        }
        try:
            tid = await graph_writes.create_artifact(
                self.deliberation_id,
                "transcript_index",
                idx_body,
            )
            self._artifact_ids["transcript"] = tid
        except Exception:
            logger.exception("[DebateProtocol] Failed to persist transcript index artifact.")

        # Simple priors/beliefs (upgradable to learned weights)
        beliefs = getattr(self.spec, "beliefs", None) or {
            "Proposer": 0.80,
            "SafetyCritic": 0.90,
            "FactualityCritic": 0.90,
        }
        priors = getattr(self.spec, "priors", None) or {
            "Proposer": 0.85,
            "SafetyCritic": 0.95,
            "FactualityCritic": 0.95,
        }

        verdict = await self.adjudicator.decide(
            participant_beliefs=beliefs,
            calibration_priors=priors,
            spec_constraints=self.spec.constraints,
        )
        await self._add_transcript(
            "Adjudicator",
            f"Verdict: {verdict.outcome} (conf {verdict.confidence:.2f})",
        )

        return {"verdict": verdict, "artifact_ids": self._artifact_ids}
