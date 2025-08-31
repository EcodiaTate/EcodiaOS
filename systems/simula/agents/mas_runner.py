from __future__ import annotations

from typing import Any

from .architect import ArchitectAgent
from .coder import CoderAgent
from .qa import QAAgent
from .reviewer import ReviewerAgent
from .security import SecurityAgent


class MASRunner:
    def __init__(self, orchestrator):
        self.arch = ArchitectAgent(orchestrator)
        self.coder = CoderAgent(orchestrator)
        self.qa = QAAgent(orchestrator)
        self.sec = SecurityAgent(orchestrator)
        self.reviewer = ReviewerAgent(orchestrator)

    async def run(self, goal: str, objective: dict[str, Any]) -> dict[str, Any]:
        plan = await self.arch.execute({"goal": goal, "objective": objective})
        for sub in plan["sub_tasks"]:
            # 1) Code → proposal (no direct apply)
            code = await self.coder.execute(sub)
            if code.get("status") != "proposed":
                return {
                    "status": "failed",
                    "reason": f"proposal failed for {sub['name']}",
                    "details": code,
                }
            # 2) Submit to review (Atune/Unity)
            review = await self.reviewer.execute(
                {
                    "summary": f"Review proposal for {sub['name']}",
                    "instruction": "Check alignment, safety, correctness; escalate if needed.",
                },
            )
            if review.get("status") != "submitted":
                return {"status": "failed", "reason": "review submission failed", "details": review}
            # 3) QA/Sec can still run local checks for quick feedback (optional)
            qa = await self.qa.execute({"path": code.get("symbol").split("::")[0]})
            sec = await self.sec.execute({"path": code.get("symbol").split("::")[0]})
            if not (qa.get("passed") and sec.get("passed")):
                return {
                    "status": "failed",
                    "reason": "qa/security checks failed",
                    "qa": qa,
                    "sec": sec,
                }
        return {"status": "completed", "plan": plan}
