# systems/qora/core/services.py
# FINAL & CONSOLIDATED FILE
from __future__ import annotations

import asyncio
from typing import Any

from core.llm.call_llm import execute_llm_call
from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query


# --- Service 1: Constitution ---
class ConstitutionService:
    # ... (implementation from previous response, no changes needed)
    async def get_applicable_constitution(self, agent: str, profile: str) -> list[dict[str, Any]]:
        query = """
        MATCH (p:Profile {agent: $agent, name: $profile})
        WHERE NOT (p)-[:SUPERSEDED_BY]->()
        MATCH (p)-[:INCLUDES]->(r:ConstitutionRule)
        WHERE r.active = true
        RETURN r.name as name, r.priority as priority, r.text as text
        ORDER BY r.priority DESC
        """
        results = await cypher_query(query, {"agent": agent, "profile": profile})
        return results if results else []


# --- Service 2: Multi-Agent Deliberation ---
class DeliberationService:
    # ... (implementation from previous response, no changes needed)
    CRITIC_PANEL = [
        {
            "role": "SecurityCritic",
            "model": "gpt-5-security-tuned",
            "prompt": "You are a world-class cybersecurity expert... If no issues, respond ONLY with 'LGTM'.",
        },
        {
            "role": "EfficiencyCritic",
            "model": "gemini-2.5-pro-code-analysis",
            "prompt": "You are a principal engineer obsessed with performance... If no issues, respond ONLY with 'LGTM'.",
        },
        {
            "role": "ReadabilityCritic",
            "model": "gemini-2.5-pro",
            "prompt": "You are a senior developer who values clean, readable code... If no issues, respond ONLY with 'LGTM'.",
        },
    ]

    async def _run_critic(self, critic: dict, diff: str) -> dict[str, str]:
        messages = [
            {"role": "system", "content": critic["prompt"]},
            {
                "role": "user",
                "content": f"Here is the code diff to review:\n\n```diff\n{diff}\n```",
            },
        ]
        try:
            response = await execute_llm_call(
                messages=messages,
                provider_overrides={
                    "model": critic["model"],
                    "temperature": 0.05,
                    "max_tokens": 512,
                },
            )
            feedback = response.get("text", "No feedback provided.").strip()
            return {"role": critic["role"], "feedback": feedback}
        except Exception as e:
            return {"role": critic["role"], "feedback": f"Error during critique: {e!r}"}

    async def request_critique(self, diff: str) -> dict[str, Any]:
        tasks = [self._run_critic(critic, diff) for critic in self.CRITIC_PANEL]
        results = await asyncio.gather(*tasks)
        final_feedback = [
            res
            for res in results
            if "LGTM" not in res["feedback"].upper()
            and "Error" not in res["feedback"]
            and res["feedback"]
        ]
        return {
            "critiques": final_feedback,
            "passed": len(final_feedback) == 0,
            "summary": f"Deliberation complete. {len(final_feedback)} actionable critiques found.",
        }


# --- Service 3: Learning from Experience ---
class LearningService:
    """
    Provides services for learning from past agent experiences stored in the graph.
    [cite: eos_bible.md - Synapse (arm selection + learning)]
    """

    async def find_similar_failures(self, goal: str, top_k: int = 3) -> list[dict[str, Any]]:
        """
        Finds past failures (and their solutions) that are semantically similar to the current goal.
        """
        # 1. Create an embedding for the current goal.
        goal_embedding = await get_embedding(goal, task_type="RETRIEVAL_QUERY")

        # 2. Use the vector index to find the most similar :Conflict nodes.
        # This query finds conflicts, then traverses to find their successful :Solution.
        query = """
        CALL db.index.vector.queryNodes('conflict_embedding', $top_k, $embedding)
        YIELD node AS conflict, score
        // After finding a similar conflict, find its resolution
        OPTIONAL MATCH (conflict)-[:RESOLVED_BY]->(solution:Solution)
        RETURN
            conflict.description as description,
            conflict.context.goal as goal,
            solution.diff as solution_diff,
            score
        ORDER BY score DESC
        """
        params = {"embedding": goal_embedding, "top_k": top_k}
        results = await cypher_query(query, params)

        # Filter for results that have a valid solution
        return [res for res in results if res.get("solution_diff")] if results else []


# --- Singleton Instances ---
constitution_service = ConstitutionService()
deliberation_service = DeliberationService()
learning_service = LearningService()
