from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .base import BaseAgent


class MetaAgent(BaseAgent):
    async def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        # Read simple telemetry if available to pick a self-upgrade objective
        logs = Path(".simula/telemetry.jsonl")
        failing_tool = None
        if logs.exists():
            counts = {}
            for line in logs.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(line)
                    if e.get("status") == "error":
                        counts[e.get("tool_name", "?")] = counts.get(e.get("tool_name", "?"), 0) + 1
                except Exception:
                    pass
            failing_tool = max(counts, key=counts.get) if counts else None

        title = (
            f"Reduce failures in tool '{failing_tool}'"
            if failing_tool
            else "Improve codegen stability"
        )
        obj = {
            "id": f"simula_self_upgrade_{uuid4().hex[:8]}",
            "title": title,
            "mode": "mas",
            "paths": ["systems/simula/"],
            "acceptance": {"tests": ["tests/"]},
        }
        try:
            return await self.orchestrator.run(goal=obj["title"], objective_dict=obj)
        except Exception as e:
            return {"status": "no_action", "reason": str(e)}
