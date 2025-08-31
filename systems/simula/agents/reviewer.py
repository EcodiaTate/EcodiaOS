# systems/simula/agents/reviewer.py
from __future__ import annotations

from typing import Any

from .base import BaseAgent


class ReviewerAgent(BaseAgent):
    async def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        """
        Thin reviewer that submits the current proposal for Atune/Unity review.
        Expects a 'summary' and optional 'instruction' in task.
        """
        summary = task.get("summary") or "Review the current code evolution proposal."
        instruction = task.get("instruction", "")
        res = await self.orchestrator.call_tool(
            "submit_code_for_multi_agent_review",
            {"summary": summary, "instruction": instruction},
        )
        return {"status": res.get("status", "error"), "review": res}
