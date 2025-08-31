from __future__ import annotations

from typing import Any

from .base import BaseAgent


class ArchitectAgent(BaseAgent):
    async def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        obj = task.get("objective", {})
        target = obj.get("target_symbol") or obj.get("target_file") or "app/core.py::main"
        # Always pull dossier first (makes plan reliable)
        await self.orchestrator.call_tool(
            "get_context_dossier",
            {"target_fqname": target, "intent": obj.get("intent", "implement")},
        )
        plan = [
            {
                "name": f"implement::{target}",
                "intent": obj.get("intent", "implement feature"),
                "targets": [{"symbol": target}],
                "contracts": obj.get("contracts", {}),
                "perf_budget_ms": obj.get("perf_budget_ms", 100),
            },
        ]
        return {"sub_tasks": plan, "notes": "architect_v1"}
