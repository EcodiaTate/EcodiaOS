# systems/simula/code_sim/prompts.py
"""
Prompt builders for Simula Godmode

REFACTORED:
- These functions now ONLY build the user-facing part of the prompt.
- They no longer fetch or inject identity; the central LLM Bus handles that.
- They return a single user prompt string, not a full message list.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ---- Cross-system deps for context gathering (Unchanged) --------------------
from systems.evo.core.EvoEngine.dao import get_recent_codegen_feedback
from systems.unity.core.logger.dao import get_recent_unity_reviews

# ---- Constants --------------------------------------------------------------
REPO_ROOT = Path(os.environ.get("SIMULA_REPO_ROOT", "/workspace")).resolve()


# ---- Helpers (Unchanged) ----------------------------------------------------


def _read_file_snippet(path: Path, max_lines: int = 60) -> str:
    """
    Read head/tail of a file for compact context. Gracefully handles missing files.
    """
    try:
        if not path.is_file():
            return "[[ FILE NOT FOUND ]]"
        lines = path.read_text(errors="ignore").splitlines()
        if len(lines) <= max_lines:
            return "\n".join(lines)
        half = max_lines // 2
        head = "\n".join(lines[:half])
        tail = "\n".join(lines[-half:])
        return f"{head}\n...\n{tail}"
    except Exception:
        return "[[ FILE UNREADABLE ]]"


def _gather_repo_context(targets: list[dict[str, Any]], max_lines: int = 60) -> str:
    """
    Lightweight repo context aggregator using file head/tail snippets.
    """
    blocks: list[str] = []
    for t in targets or []:
        rel = t.get("path")
        if not rel:
            continue
        abs_path = (REPO_ROOT / rel).resolve()
        snippet = _read_file_snippet(abs_path, max_lines=max_lines)
        blocks.append(f"### File: {rel}\n```\n{snippet}\n```")
    return "\n\n".join(blocks)


# ---- DEPRECATED HELPERS -----------------------------------------------------

# The _ensure_identity and fetch_identity_context logic is now fully obsolete.
# The LLM Bus is solely responsible for composing the agent's identity.

# ---- Public API (Refactored) -------------------------------------------------


async def build_plan_prompt(
    spec: str,
    targets: list[dict[str, Any]],
) -> str:
    """
    Builds the user content for the planning prompt.

    REFACTORED: Returns a single string for the user prompt. Does not include
    system messages or identity context.
    """
    # Side signals (best-effort; don't explode if stores are empty)
    evo_feedback = await get_recent_codegen_feedback(limit=10)
    unity_reviews = await get_recent_unity_reviews(limit=5)

    repo_ctx = _gather_repo_context(targets, max_lines=60)

    # This function now assembles only the user-facing content.
    # The LLM Bus will prepend the full system prompt and identity from Equor.
    return (
        f"## SPEC\n{spec}\n\n"
        f"## RECENT EVO FEEDBACK (last 10)\n```json\n{json.dumps(evo_feedback, indent=2)}\n```\n\n"
        f"## RECENT UNITY REVIEWS (last 5)\n```json\n{json.dumps(unity_reviews, indent=2)}\n```\n\n"
        f"## TARGET FILE CONTEXT\n{repo_ctx}\n\n"
        "## INSTRUCTIONS\n"
        "Only output VALID JSON with exactly this schema:\n"
        '{ "plan": { "files": [ { "path": "<rel>", '
        '"mode": "<patch|full|scaffold|imports|typing|error_paths>", '
        '"signature": "<optional>", "notes": "<why>" } ] }, '
        '"notes": "<strategy>" }\n'
        "Prefer the smallest atomic plan that satisfies the spec. "
        "Avoid risky rewrites; use patches where possible."
    )


async def build_file_prompt(
    spec: str,
    file_plan: dict[str, Any],
) -> str:
    """
    Builds the user content for the single-file generation/patch prompt.

    REFACTORED: Returns a single string. Does not include system messages
    or identity context.
    """
    rel = file_plan.get("path", "")
    abs_path = (REPO_ROOT / rel).resolve() if rel else REPO_ROOT
    snippet = _read_file_snippet(abs_path, max_lines=240)

    include_current = str(file_plan.get("mode", "")).lower() in {
        "patch",
        "imports",
        "typing",
        "error_paths",
    }

    # Assemble all necessary context into a single string.
    parts: list[str] = [
        f"## SPEC\n{spec}",
        f"## FILE PLAN\n```json\n{json.dumps(file_plan, indent=2)}\n```",
    ]
    if include_current:
        parts.append(f"## CURRENT CONTENT OF {rel}\n```\n{snippet}\n```")

    parts.append(
        "## INSTRUCTIONS\n"
        "Output ONLY the FINAL, complete file content (not a diff). "
        "Follow PEP8 and established project style. "
        "If unsure about small details, choose the safest reasonable default.",
    )

    return "\n\n".join(parts)
