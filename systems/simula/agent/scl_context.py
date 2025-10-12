# systems/simula/agent/scl_context.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from systems.simula.nscs.agent_tools import memory_read, memory_write
from systems.synapse.schemas import ArmScore

log = logging.getLogger(__name__)


class FileCard(BaseModel):
    path: str
    summary: str
    relevance_score: float = 0.0
    entities: list[str] = Field(default_factory=list)


class ToolHint(BaseModel):
    signature: str
    description: str
    relevance_score: float = 0.0


class WorkingContext(BaseModel):
    """A compact, token-budgeted context object for the deliberation room."""

    goal: str
    target_fqname: str | None
    strategy_arm: ArmScore
    file_cards: list[FileCard] = Field(default_factory=list)
    tool_hints: list[ToolHint] = Field(default_factory=list)
    history_summary: str
    blackboard_insights: dict[str, Any] = Field(default_factory=dict)

    # NEW: safe scratchpads for templates / orchestrator
    context_vars: dict[str, Any] = Field(default_factory=dict)
    extras: dict[str, Any] = Field(default_factory=dict)


class Blackboard:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history_key = f"simula_session_{session_id}_history"
        self.turn_history: list[dict[str, Any]] = []
        self.insights: dict[str, Any] = {}  # For ephemeral data like last_error

    async def load_from_memory(self):
        result = await memory_read(key=self.history_key)
        self.turn_history = (
            (result.get("value") or []) if isinstance(result.get("value"), list) else []
        )

    async def persist_to_memory(self):
        await memory_write(key=self.history_key, value=self.turn_history)

    def get_history_summary(self) -> str:
        if not self.turn_history:
            return "This is the first turn. No prior history."
        last_turn = self.turn_history[-1]
        score = last_turn.get("utility_score", "N/A")
        reason = last_turn.get("utility_reasoning", "No reasoning recorded.")
        return f"Last turn (Turn {len(self.turn_history)}) scored {score}. Reasoning: '{reason}'"

    async def record_turn(
        self,
        *,
        goal: str,
        plan: dict,
        execution_outcomes: dict,
        utility_score: float,
        utility_reasoning: str,
    ):
        turn_summary = {
            "turn_number": len(self.turn_history) + 1,
            "goal_for_turn": goal,
            "plan_thought": plan.get("interim_thought"),
            "plan_actions": plan.get("plan"),
            "execution_outcomes": execution_outcomes,
            "utility_score": utility_score,
            "utility_reasoning": utility_reasoning,
        }
        self.turn_history.append(turn_summary)


async def synthesize_context(
    *,
    strategy_arm: ArmScore,
    goal: str,
    target_fqname: str | None,
    dossier: dict[str, Any],
    blackboard: Blackboard,
    lensed_tools: list[dict[str, Any]],  # MODIFIED: Accept the filtered tools
) -> WorkingContext:
    file_cards = []
    if dossier:
        for file_path, content in dossier.items():
            if isinstance(content, str) and content.strip():
                first_lines = content.strip().splitlines()[:5]
                summary = " ".join(first_lines)
                if len(summary) > 250:
                    summary = summary[:250] + "..."
            else:
                summary = f"Content of file {file_path} is empty or not a string."
            file_cards.append(FileCard(path=file_path, summary=summary, relevance_score=0.9))

    # MODIFIED: Dynamically create ToolHints from the lensed tool list, replacing the hardcoded version.
    tool_hints = [
        ToolHint(
            signature=tool.get("signature", tool.get("name")),
            description=tool.get("description", ""),
            relevance_score=0.9,  # Assign a default high relevance for tools passed through the lens
        )
        for tool in lensed_tools
    ]

    wc = WorkingContext(
        goal=goal,
        target_fqname=target_fqname,
        strategy_arm=strategy_arm,
        file_cards=file_cards,
        tool_hints=tool_hints,
        history_summary=blackboard.get_history_summary(),
        blackboard_insights=blackboard.insights,
    )

    # Ensure templates ALWAYS have an object-like strategy_arm and convenient mirrors
    sa_dict = strategy_arm.model_dump(mode="json")
    wc.context_vars["strategy_arm"] = sa_dict
    wc.context_vars["strategy_arm_id"] = sa_dict.get("arm_id")
    wc.extras["strategy_arm"] = sa_dict
    wc.extras["strategy_arm_id"] = sa_dict.get("arm_id")

    return wc
