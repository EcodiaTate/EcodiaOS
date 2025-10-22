# systems/simula/agent/scl_context.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from systems.simula.nscs.agent_tools import memory_read, memory_write
from systems.synapse.schemas import ArmScore

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class FileCard(BaseModel):
    path: str
    summary: str
    relevance_score: float = 0.0
    entities: list[str] = Field(default_factory=list)


class ToolHint(BaseModel):
    """
    Prompt-time metadata about a tool.
    NOTE: 'name' is the canonical ID used by execution (e.g., 'apply_refactor').
    """
    name: str
    signature: str
    description: str
    relevance_score: float = 0.0


class WorkingContext(BaseModel):
    """A compact, token-budgeted context object for the deliberation room."""

    goal: str
    target_fqname: str | None
    strategy_arm: ArmScore

    # Dossier-derived file context
    file_cards: list[FileCard] = Field(default_factory=list)

    # Prompt-time tool metadata (advisory for LLM)…
    tool_hints: list[ToolHint] = Field(default_factory=list)
    # …and the authoritative runtime allowlist (must match tool IDs used by dispatcher)
    allowed_tools: list[str] = Field(default_factory=list)

    # Human summary of prior turns
    history_summary: str

    # Blackboard-derived misc insights (safe)
    blackboard_insights: dict[str, Any] = Field(default_factory=dict)

    # Template/runtime convenience mirrors (ALWAYS safe, non-None)
    # Matches prompt partials that expect these at top level:
    #   - tools_catalog.candidates[*].function.{name,description}
    #   - lensed_tools[*].{name,description}
    tools_catalog: dict[str, Any] = Field(default_factory=lambda: {"candidates": []})
    lensed_tools: list[dict[str, Any]] = Field(default_factory=list)

    # Safe scratchpads for templates / orchestrator
    context_vars: dict[str, Any] = Field(default_factory=dict)
    extras: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Blackboard
# ──────────────────────────────────────────────────────────────────────────────

class Blackboard:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history_key = f"simula_session_{session_id}_history"
        self.turn_history: list[dict[str, Any]] = []
        self.insights: dict[str, Any] = {}  # For ephemeral data like last_error

    async def load_from_memory(self):
        result = await memory_read(key=self.history_key)
        value = result.get("value") if isinstance(result, dict) else None
        self.turn_history = value if isinstance(value, list) else []

    async def persist_to_memory(self):
        await memory_write(key=self.history_key, value=self.turn_history)

    def get_history_summary(self) -> str:
        if not self.turn_history:
            return "This is the first turn. No prior history."
        last_turn = self.turn_history[-1] or {}
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
            "plan_thought": plan.get("interim_thought") if isinstance(plan, dict) else None,
            "plan_actions": plan.get("plan") if isinstance(plan, dict) else None,
            "execution_outcomes": execution_outcomes,
            "utility_score": utility_score,
            "utility_reasoning": utility_reasoning,
        }
        self.turn_history.append(turn_summary)


# ──────────────────────────────────────────────────────────────────────────────
# Context synthesis
# ──────────────────────────────────────────────────────────────────────────────

_MAX_SUMMARY_CHARS = 250


def _summarize_content_preview(content: Any) -> str:
    if isinstance(content, str) and content.strip():
        first_lines = content.strip().splitlines()[:5]
        summary = " ".join(first_lines).strip()
        if len(summary) > _MAX_SUMMARY_CHARS:
            summary = summary[:_MAX_SUMMARY_CHARS] + "..."
        return summary
    return "Content is empty or not a string."


def _normalize_lensed_tools(lensed_tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return a safe, minimal list[{name, description}] for templates."""
    safe_list: list[dict[str, Any]] = []
    for t in (lensed_tools or []):
        name = (t.get("name") or "").strip()
        desc = (t.get("description") or "") or "No description."
        if not name:
            continue
        safe_list.append({"name": name, "description": desc})
    return safe_list


def _make_tools_catalog_candidates(lensed_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert normalized lensed_tools into the shape expected by the Jinja partial:
      tools_catalog.candidates[*].function.{name, description}
    """
    cands: list[dict[str, Any]] = []
    for t in lensed_tools:
        cands.append({"function": {"name": t["name"], "description": t["description"]}})
    return cands


async def synthesize_context(
    *,
    strategy_arm: ArmScore,
    goal: str,
    target_fqname: str | None,
    dossier: dict[str, Any] | None,
    blackboard: Blackboard,
    lensed_tools: list[dict[str, Any]] | None,  # [{name, signature?, description?}, ...]
) -> WorkingContext:
    # ---- Build file cards from dossier (defensive) ----
    file_cards: list[FileCard] = []
    if isinstance(dossier, dict) and dossier:
        for file_path, content in dossier.items():
            try:
                path_str = str(file_path)
            except Exception:
                path_str = "<unknown>"
            summary = _summarize_content_preview(content)
            file_cards.append(FileCard(path=path_str, summary=summary, relevance_score=0.9))

    # ---- Build prompt-time tool hints + runtime allowlist (defensive) ----
    tool_hints: list[ToolHint] = []
    allowed_tools: list[str] = []

    # Normalize input lensed_tools to [{name, description}]
    normalized_lensed = _normalize_lensed_tools(lensed_tools)

    for tool in normalized_lensed:
        name = tool["name"]
        desc = tool["description"]
        # Signature isn’t always available; fall back to name
        hint = ToolHint(
            name=name,
            signature=name,
            description=desc,
            relevance_score=0.9,
        )
        tool_hints.append(hint)
        allowed_tools.append(name)

    # ---- Construct WorkingContext (never None for iterables) ----
    history_summary = blackboard.get_history_summary() or ""
    wc = WorkingContext(
        goal=goal or "",
        target_fqname=target_fqname,
        strategy_arm=strategy_arm,
        file_cards=file_cards or [],
        tool_hints=tool_hints or [],
        allowed_tools=allowed_tools or [],
        history_summary=history_summary,
        blackboard_insights=blackboard.insights or {},
        tools_catalog={"candidates": _make_tools_catalog_candidates(normalized_lensed)},
        lensed_tools=normalized_lensed,
    )

    # ---- Ensure templates ALWAYS have strategy_arm object and mirrors ----
    sa_dict = strategy_arm.model_dump(mode="json")
    wc.context_vars["strategy_arm"] = sa_dict
    wc.context_vars["strategy_arm_id"] = sa_dict.get("arm_id")

    # Mirror into extras for non-template consumers
    wc.extras["strategy_arm"] = sa_dict
    wc.extras["strategy_arm_id"] = sa_dict.get("arm_id")

    # Also expose tools to both template and runtime layers
    wc.context_vars["allowed_tools"] = list(allowed_tools)
    wc.context_vars["tool_hints"] = [h.model_dump(mode="json") for h in tool_hints]
    wc.extras["allowed_tools"] = list(allowed_tools)
    wc.extras["tool_hints"] = [h.model_dump(mode="json") for h in tool_hints]

    # Surface frequently used top-levels into context_vars (optional, but handy)
    wc.context_vars["file_cards"] = [fc.model_dump(mode="json") for fc in file_cards]
    wc.context_vars["tools_catalog"] = wc.tools_catalog
    wc.context_vars["lensed_tools"] = wc.lensed_tools
    wc.context_vars["history_summary"] = wc.history_summary or ""

    log.info(
        "[SCL-CTX] Synthesized context | files=%d tools_allowed=%d",
        len(file_cards),
        len(allowed_tools),
    )
    return wc
