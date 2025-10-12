# systems/qora/core/deliberation/service.py
# CONSOLIDATED FILE
from __future__ import annotations

import asyncio
from typing import Any

from core.llm.call_llm import execute_llm_call


class DeliberationService:
    """
    Orchestrates a multi-agent, multi-provider critique of a code diff.
    Leverages different models for their unique strengths to form a powerful review panel.
    [cite: eos_bible.md - Unity (deliberation -> VerdictModel)]
    """

    CRITIC_PANEL = [
        {
            "role": "SecurityCritic",
            "model": "gpt-5-security-tuned",  # Hypothetical best-in-class security model
            "prompt": "You are a world-class cybersecurity expert and penetration tester. Your sole focus is security. Review this code diff for vulnerabilities like injection, XSS, improper authentication/authorization, data leaks, or unsafe deserialization. Be concise, specific, and technical. If no issues, respond ONLY with 'LGTM'.",
        },
        {
            "role": "EfficiencyCritic",
            "model": "gemini-2.5-pro-code-analysis",  # Hypothetical best-in-class for performance
            "prompt": "You are a principal engineer at a high-frequency trading firm, obsessed with performance and efficiency. Review this code diff for performance anti-patterns: N+1 queries, blocking I/O in async code, inefficient loops, excessive memory allocation, or poor algorithm choice. Be concise. If no issues, respond ONLY with 'LGTM'.",
        },
        {
            "role": "ReadabilityCritic",
            "model": "gemini-2.5-pro",
            "prompt": "You are a senior developer and author of a popular book on clean code. You value long-term maintainability above all else. Review this diff for style violations (PEP8), overly complex logic, poor naming, lack of comments where needed, and unclear abstractions. Be concise. If no issues, respond ONLY with 'LGTM'.",
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
        """
        Submits a diff to the full critic panel and aggregates actionable feedback.
        """
        tasks = [self._run_critic(critic, diff) for critic in self.CRITIC_PANEL]
        results = await asyncio.gather(*tasks)

        # Filter out positive feedback ("LGTM") and errors to keep the feedback actionable.
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
            "summary": f"Deliberation complete. {len(final_feedback)} actionable critiques found by the panel.",
        }


deliberation_service = DeliberationService()
