# systems/simula/agents/qa.py  (upgrade)
from __future__ import annotations

from typing import Any

from systems.simula.code_sim.evaluators.impact import compute_impact

from .base import BaseAgent


class QAAgent(BaseAgent):
    async def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        """
        Impact-driven QA pass:
        - compute impact
        - run focused tests (-k), then full suite fallback via NSCS tools (no orchestrator edits)
        """
        task.get("path") or "."
        impact = compute_impact(task.get("diff", ""), workspace_root=".")
        # Prefer changed tests if provided, else whole suite
        k_expr = impact.k_expr
        if (
            hasattr(self.orchestrator, "internal_tools")
            and "run_tests_k" in self.orchestrator.internal_tools
        ):
            res = await self.orchestrator.call_tool(
                "run_tests_k",
                {"paths": ["tests"], "k_expr": k_expr, "timeout_sec": 600},
            )
            if res.get("status") == "success":
                return {"passed": True, "strategy": "focused", "k": k_expr}
        # fallback to normal tests
        res = await self.orchestrator.call_tool(
            "run_tests",
            {"paths": ["tests"], "timeout_sec": 900},
        )
        return {"passed": res.get("status") == "success", "strategy": "full"}
