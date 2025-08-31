# systems/simula/agent/orchestrator/context.py
# --- PROJECT SENTINEL UPGRADE ---
from __future__ import annotations

import json
import pathlib
import time
from typing import Any


class ContextStore:
    """A stateful, persisted working memory for a single agent run."""

    def __init__(self, run_dir: str):
        self.run_dir = run_dir
        self.path = pathlib.Path(run_dir) / "session_state.json"
        self.state: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
            else:
                self.state = self._default_state()
        except Exception:
            self.state = self._default_state()

    def _default_state(self) -> dict[str, Any]:
        """The canonical structure for a new session's state."""
        return {
            "status": "initializing",  # e.g., planning, generating, validating, failed
            "plan": {},  # The high-level plan from the user/planner
            "dossier": {},  # Rich context for the current task
            "failures": [],  # A log of failed tool/validation steps
            "facts": {},  # General key-value memory
            "summaries": [],  # High-level history for the LLM
            "tools_cache": {},  # Cache for tool call results
        }

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = json.dumps(self.state, ensure_ascii=False, indent=2, default=str)
            self.path.write_text(tmp, encoding="utf-8")
        except Exception:
            # Never crash the orchestrator on a persistence failure
            pass

    # --- High-level state modifiers ---
    def set_status(self, status: str) -> None:
        self.state["status"] = status
        self.save()

    def update_dossier(self, dossier: dict[str, Any]) -> None:
        self.state["dossier"] = dossier
        self.save()

    def add_failure(self, tool_name: str, reason: str, params: dict | None = None) -> None:
        self.state.setdefault("failures", []).append(
            {
                "tool_name": tool_name,
                "reason": reason,
                "params": params or {},
                "timestamp": time.time(),
            },
        )
        self.save()

    def remember_fact(self, key: str, value: Any) -> None:
        self.state.setdefault("facts", {})[key] = value
        self.save()

    def get_fact(self, key: str, default=None) -> Any:
        return self.state.get("facts", {}).get(key, default)

    def push_summary(self, text: str, max_items: int = 8) -> None:
        summaries = self.state.setdefault("summaries", [])
        summaries.append(text[:2000])
        self.state["summaries"] = summaries[-max_items:]
        self.save()
