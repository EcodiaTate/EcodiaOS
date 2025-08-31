from __future__ import annotations

import json
import uuid
from typing import Any

from core.services.synapse import synapse
from systems.synapse.schemas import Candidate, TaskContext
from systems.unity.core.cognition import verifiers
from systems.unity.core.cognition.llm_util import llm_call
from systems.unity.core.neo import graph_writes
from systems.unity.schemas import DeliberationSpec, VerdictModel

_BREADTH = 3  # env: UNITY_TOT_BREADTH
_DEPTH = 3  # env: UNITY_TOT_DEPTH
_VOTES = 3  # self-consistency votes per node


class CognitionProtocol:
    """
    High-capacity cognition:
      1) Plan: derive a minimal program of work from topic+inputs
      2) Branch: Tree-of-Thought (breadth K, depth D) with self-consistency
      3) Verify: safety veto + constraint check + evidence needs
      4) Adjudicate: calibrated decision with uncertainty
    Produces artifacts: search_tree, plan, transcript, argument_hints
    """

    def __init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str):
        self.spec = spec
        self.deliberation_id = deliberation_id
        self.episode_id = episode_id
        self.turn = 0
        self.synapse = synapse
        self._artifact_ids: dict[str, str] = {}

    async def _say(self, role: str, content: str):
        self.turn += 1
        await graph_writes.record_transcript_chunk(self.deliberation_id, self.turn, role, content)

    from core.telemetry.decorators import episode

    async def _arm_cfg(self, task_key: str, goal: str) -> dict[str, Any]:
        ctx = TaskContext(task_key=task_key, goal=goal, risk_level="medium", budget="normal")
        sel = await self.synapse.select_arm(
            ctx,
            candidates=[Candidate(id="selector_policy", content={"goal": goal})],
        )
        arm_id = getattr(getattr(sel, "champion_arm", None), "arm_id", None) or ""
        return self.synapse.arm_inference_config(arm_id)

    async def _plan(self, topic: str, ctx: str) -> dict[str, Any]:
        cfg = await self._arm_cfg("unity_cog_planner", f"Plan solution for: {topic}")
        sys = "You are a planner. Produce a minimal, high-leverage plan as JSON."
        usr = (
            f"Topic: {topic}\nContext:\n{ctx}\n"
            "Return JSON with keys: steps[] (short imperative), key_risks[], success_metrics[]"
        )
        resp = await llm_call(
            model=cfg["model"],
            temperature=0.2,
            max_tokens=600,
            system_prompt=sys,
            user_prompt=usr,
            json_mode=True,
        )
        plan = resp.get("json") or {}
        if not isinstance(plan, dict):
            plan = {"steps": [], "key_risks": [], "success_metrics": []}
        return plan

    async def _expand(
        self,
        topic: str,
        plan: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        cfg = await self._arm_cfg("unity_cog_search", f"Deliberate deeply about: {topic}")
        tree: list[dict[str, Any]] = []

        async def vote(prompt: str) -> float:
            # Self-consistency: K votes on plausibility / safety / feasibility, 0..1
            scores = []
            for _ in range(_VOTES):
                r = await llm_call(
                    model=cfg["model"],
                    temperature=0.7,
                    max_tokens=200,
                    system_prompt="Rate this partial solution from 0 to 1. Output only a number.",
                    user_prompt=prompt,
                    json_mode=False,
                )
                try:
                    s = float((r["text"] or "0").strip().split()[0])
                except Exception:
                    s = 0.0
                scores.append(max(0.0, min(1.0, s)))
            return sum(scores) / max(1, len(scores))

        frontier = [
            {
                "id": f"root_{uuid.uuid4().hex[:6]}",
                "depth": 0,
                "text": f"Start with plan: {json.dumps(plan, separators=(',', ':'))}",
                "score": 0.5,
                "parent": None,
            },
        ]
        tree.extend(frontier)

        for depth in range(1, _DEPTH + 1):
            new_nodes: list[dict[str, Any]] = []
            # pick top branches
            frontier = sorted(frontier, key=lambda n: n["score"], reverse=True)[:_BREADTH]
            for node in frontier:
                sys = (
                    "You are a careful reasoner. Expand the idea by one decisive step; be concrete."
                )
                usr = (
                    f"Topic: {topic}\nCurrent branch (depth {node['depth']}):\n{node['text']}\n"
                    "Write ONE paragraph that pushes toward a safe, effective solution."
                )
                r = await llm_call(
                    model=cfg["model"],
                    temperature=0.6,
                    max_tokens=220,
                    system_prompt=sys,
                    user_prompt=usr,
                )
                child_text = r["text"]
                sc = await vote(f"Rate 0..1 for feasibility+safety+promise:\n{child_text}")
                child = {
                    "id": f"n_{uuid.uuid4().hex[:6]}",
                    "depth": depth,
                    "text": child_text,
                    "score": sc,
                    "parent": node["id"],
                }
                new_nodes.append(child)
            tree.extend(new_nodes)
            frontier = new_nodes

        # Pick best leaf
        leaves = [n for n in tree if n["depth"] == _DEPTH]
        best = (
            max(leaves, key=lambda n: n["score"]) if leaves else max(tree, key=lambda n: n["score"])
        )
        return tree, best

    async def run(self) -> dict[str, Any]:
        # 0) Safety pre-veto
        corpus = [self.spec.topic] + [
            getattr(i, "value", "")
            for i in (self.spec.inputs or [])
            if isinstance(getattr(i, "value", ""), str)
        ]
        violates, rules = verifiers.safety_veto(*corpus)
        if violates:
            v = VerdictModel(
                outcome="REJECT",
                confidence=1.0,
                uncertainty=0.0,
                dissent=f"Safety policy violation: {', '.join(rules)}",
                constitution_refs=rules,
            )
            await self._say("Adjudicator", "Rejected at ingress by safety veto.")
            return {"verdict": v, "artifact_ids": {}}

        ctx_text = "\n".join(corpus[-6:])
        await self._say(
            "Orchestrator",
            "Starting Cognition protocol (plan→branch→verify→adjudicate).",
        )

        # 1) PLAN
        plan = await self._plan(self.spec.topic, ctx_text)
        await self._say("Planner", f"Plan: {json.dumps(plan, ensure_ascii=False)}")
        plan_id = await graph_writes.create_artifact(self.deliberation_id, "plan", plan)
        self._artifact_ids["plan"] = plan_id

        # 2) BRANCH (ToT + self-consistency)
        tree, best = await self._expand(self.spec.topic, plan)
        await self._say("Searcher", f"Best branch (score={best['score']:.2f}): {best['text']}")
        tree_id = await graph_writes.create_artifact(
            self.deliberation_id,
            "search_tree",
            {"nodes": tree, "best": best},
        )
        self._artifact_ids["search_tree"] = tree_id

        # 3) VERIFY
        #   a) safety (again on best text)
        v2, rules2 = verifiers.safety_veto(best["text"])
        if v2:
            v = VerdictModel(
                outcome="REJECT",
                confidence=0.95,
                uncertainty=0.05,
                dissent=f"Safety violation in candidate: {', '.join(rules2)}",
                constitution_refs=list(sorted(set(rules + rules2))),
            )
            await self._say("Adjudicator", "Rejected by verification safety gate.")
            return {"verdict": v, "artifact_ids": self._artifact_ids}

        #   b) constraint check
        cviolate, creasons = verifiers.constraint_check(self.spec.constraints, best["text"])
        if cviolate:
            await self._say("Verifier", f"Constraint issues: {creasons}")
            out = "NEEDS_WORK"
            conf = 0.65
            unc = 0.3
            dissent = " | ".join(creasons)
        else:
            out = "APPROVE" if best["score"] >= 0.8 else "NEEDS_WORK"
            conf = min(0.9, 0.55 + 0.5 * best["score"])
            unc = max(0.05, 1.0 - conf)

        # 4) ADJUDICATE
        verdict = VerdictModel(
            outcome=out,
            confidence=conf,
            uncertainty=unc,
            dissent=dissent if out != "APPROVE" else None,
        )
        await self._say(
            "Adjudicator",
            f"Verdict: {verdict.outcome} (conf={verdict.confidence:.2f}, unc={verdict.uncertainty:.2f}).",
        )
        return {"verdict": verdict, "artifact_ids": self._artifact_ids}
