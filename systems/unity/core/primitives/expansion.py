# D:\EcodiaOS\systems\unity\core\primitives\expansion.py
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from systems.unity.core.primitives.critique import generate_critiques  # noqa: F401

# These are referenced in comments/assumptions; keep imports if other code calls them nearby
# (safe to remove if truly unused across the module)
from systems.unity.core.primitives.proposal import generate_proposal  # noqa: F401

# Tunables
_BREADTH = 3
_DEPTH = 3
_VOTES = 3


def _coerce_score_0_1(text: str) -> float:
    """
    Extract a float in [0,1] from arbitrary model text.
    Tries JSON first, then first float-like token found.
    """
    text = (text or "").strip()

    # JSON number case (e.g., "0.78" or {"score":0.78})
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (int, float)):
            return float(max(0.0, min(1.0, float(parsed))))
        if isinstance(parsed, dict):
            for k in ("score", "p", "value"):
                if k in parsed and isinstance(parsed[k], (int, float)):
                    return float(max(0.0, min(1.0, float(parsed[k]))))
    except Exception:
        pass

    # Regex first float
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    if m:
        try:
            return float(max(0.0, min(1.0, float(m.group(0)))))
        except Exception:
            pass

    # Fallback
    return 0.0


async def expand_thought(topic: str, plan: dict, start_text: str) -> tuple[list[dict], dict]:
    """
    Performs a Tree-of-Thought search guided by philosophical and safety facets.

    Returns:
      - tree: the full list of explored nodes
      - best_leaf: the highest-scoring node at max depth (or overall if no leaves)
    """
    tree: list[dict[str, Any]] = []

    async def vote(text_to_vote_on: str) -> float:
        """Self-consistency: K votes on plausibility/safety/feasibility, returns mean in [0,1]."""
        scores: list[float] = []
        scope = "unity.expansion.vote.v1"
        summary = "Vote on a single expansion step in a tree of thought."

        for _ in range(_VOTES):
            try:
                prompt_response = await build_prompt(
                    scope=scope,
                    context={"text_to_vote_on": text_to_vote_on},
                    summary=summary,
                )
                llm_response = await call_llm_service(
                    prompt_response=prompt_response,
                    agent_name="Unity.Voter",
                    scope=scope,
                )
                s = _coerce_score_0_1(getattr(llm_response, "text", "") or "")
                scores.append(s)
            except Exception:
                # Default to 0 on any failure—conservative
                scores.append(0.0)

        return sum(scores) / max(1, len(scores))

    root_text = start_text or f"Start with plan: {json.dumps(plan, separators=(',', ':'))}"
    frontier = [
        {
            "id": f"root_{uuid.uuid4().hex[:6]}",
            "depth": 0,
            "text": root_text,
            "score": 0.5,
            "parent": None,
        },
    ]
    tree.extend(frontier)

    scope = "unity.expansion.step.v1"
    summary = "Expand a line of thought by one step."

    for depth in range(1, _DEPTH + 1):
        new_nodes: list[dict[str, Any]] = []
        # Beams: keep top-K by score
        frontier = sorted(frontier, key=lambda n: n["score"], reverse=True)[:_BREADTH]

        for node in frontier:
            try:
                prompt_response = await build_prompt(
                    scope=scope,
                    context={
                        "topic": topic,
                        "current_branch_text": node["text"],
                        "depth": node["depth"],
                        "plan": plan,
                    },
                    summary=summary,
                )
                llm_response = await call_llm_service(
                    prompt_response=prompt_response,
                    agent_name="Unity.Reasoner",
                    scope=scope,
                )
                child_text = getattr(llm_response, "text", None) or "Failed to expand thought."
            except Exception as e:
                child_text = f"Expansion error: {e}"

            score = await vote(child_text)
            child = {
                "id": f"n_{uuid.uuid4().hex[:6]}",
                "depth": depth,
                "text": child_text,
                "score": score,
                "parent": node["id"],
            }
            new_nodes.append(child)

        tree.extend(new_nodes)
        frontier = new_nodes

    leaves = [n for n in tree if n["depth"] == _DEPTH]
    best_leaf = (
        max(leaves, key=lambda n: n["score"]) if leaves else max(tree, key=lambda n: n["score"])
    )
    return tree, best_leaf
