# systems/simula/code_sim/prompts.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from systems.evo.core.EvoEngine.dao import get_recent_codegen_feedback
from systems.simula.service.services.equor_bridge import fetch_identity_context
from systems.unity.core.logger.dao import get_recent_unity_reviews

REPO_ROOT = Path(os.environ.get("SIMULA_REPO_ROOT", Path.cwd())).resolve()


def _read_file_snippet(path: Path, max_lines: int = 60) -> str:
    if not path.exists():
        return "[[ FILE NOT FOUND ]]"
    lines = path.read_text(errors="ignore").splitlines()
    if len(lines) > max_lines:
        head = "\n".join(lines[: max_lines // 2])
        tail = "\n".join(lines[-max_lines // 2 :])
        return f"{head}\n...\n{tail}"
    return "\n".join(lines)


async def _ensure_identity(spec: str, identity: dict[str, Any] | None) -> dict[str, Any]:
    """
    If the caller didn't supply an identity (or supplied a stub),
    fetch a minimal identity context via Equor. Falls back to spec preview.
    """
    if isinstance(identity, dict) and identity:
        return identity
    try:
        return await fetch_identity_context(spec)
    except Exception:
        # ultra-safe fallback; Equor unavailable
        return {"spec_preview": (spec or "")[:4000]}


async def build_plan_prompt(
    spec: str,
    targets: list[dict[str, Any]],
    identity: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """
    Build the planning prompt. If identity is not provided, it is fetched from Equor.
    """
    identity_ctx = await _ensure_identity(spec, identity)

    evo_feedback = await get_recent_codegen_feedback(limit=10)
    unity_reviews = await get_recent_unity_reviews(limit=5)

    context_blocks: list[str] = []
    for t in targets:
        rel = t.get("path")
        if not rel:
            continue
        abs_path = (REPO_ROOT / rel).resolve()
        snippet = _read_file_snippet(abs_path)
        context_blocks.append(f"### File: {rel}\n```python\n{snippet}\n```")

    identity_json = json.dumps(identity_ctx, indent=2)
    evo_json = json.dumps(evo_feedback, indent=2)
    unity_json = json.dumps(unity_reviews, indent=2)

    system_msg = {
        "role": "system",
        "content": (
            "You are the code generation engine of EcodiaOS. Produce a precise, minimal-risk plan for automated codegen.\n"
            "Use brand/tone/ethics from identity. Learn from feedback & reviews to avoid repeat mistakes.\n"
            "Only output VALID JSON with this exact schema:\n"
            '{ "plan": { "files": [ { "path": "<rel>", "mode": "<scaffold|imports|typing|error_paths|full>", '
            '"signature": "<optional>", "notes": "<why>" } ] }, "notes": "<strategy>" }\n'
            "Do not add extra fields. Prefer the smallest atomic plan that satisfies the spec."
        ),
    }
    user_msg = {
        "role": "user",
        "content": (
            f"## SPEC\n{spec}\n\n"
            f"## IDENTITY\n```json\n{identity_json}\n```\n\n"
            f"## EVO (last 10)\n```json\n{evo_json}\n```\n\n"
            f"## UNITY (last 5)\n```json\n{unity_json}\n```\n\n"
            f"## TARGET CONTEXT\n{''.join(context_blocks)}"
        ),
    }
    return [system_msg, user_msg]


async def build_file_prompt(
    spec: str,
    identity: dict[str, Any] | None = None,
    file_plan: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """
    Deep context for single-file generation/patch.
    If identity is not provided, it is fetched from Equor.
    """
    identity_ctx = await _ensure_identity(spec, identity)

    file_plan = file_plan or {}
    rel = file_plan.get("path", "")
    abs_path = (REPO_ROOT / rel).resolve() if rel else REPO_ROOT
    snippet = _read_file_snippet(abs_path, max_lines=240)

    identity_json = json.dumps(identity_ctx, indent=2)
    fp_json = json.dumps(file_plan, indent=2)

    system_msg = {
        "role": "system",
        "content": (
            "You are Code Writer. Generate the COMPLETE file content for the requested path.\n"
            "Follow PEP8, keep imports sane, include docstring and logger usage where appropriate.\n"
            "If the plan mode is 'patch', still output FULL file content (not a diff)."
        ),
    }
    user_msg = {
        "role": "user",
        "content": (
            f"## SPEC\n{spec}\n\n"
            f"## IDENTITY\n```json\n{identity_json}\n```\n\n"
            f"## FILE PLAN\n```json\n{fp_json}\n```\n\n"
            f"## CURRENT CONTENT (head/tail)\n```python\n{snippet}\n```"
        ),
    }
    return [system_msg, user_msg]
