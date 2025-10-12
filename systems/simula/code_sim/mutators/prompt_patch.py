from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from httpx import HTTPStatusError

from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from core.utils.net_api import ENDPOINTS, get_http_client

REPO_ROOT = Path(os.environ.get("SIMULA_REPO_ROOT", "/workspace")).resolve()


async def _read_snip(p: Path, n: int = 120) -> str:
    if not p.is_file():
        return ""
    try:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        if len(lines) > n:
            head = "\n".join(lines[: n // 2])
            tail = "\n".join(lines[-n // 2 :])
            return f"{head}\n...\n{tail}"
        return "\n".join(lines)
    except Exception:
        return ""


async def _targets_context(step_dict: dict[str, Any]) -> str:
    blocks = []
    # Access targets from the dictionary
    targets = step_dict.get("targets", [])
    for t in targets or []:
        rel = t.get("file") if isinstance(t, dict) else None
        if not rel:
            continue
        p = (REPO_ROOT / rel).resolve()
        snippet = await _read_snip(p)
        blocks.append(f"### {rel}\n```\n{snippet}\n```")
    return "\n".join(blocks)


def _strip_fences(text: str | None) -> str:
    if not text:
        return ""
    # capture from first '--- a/' up to a trailing ``` or end of string
    m = re.search(r"--- a/.*?(?=\n```|\Z)", text, re.DOTALL)
    return m.group(0).strip() if m else ""


def _coerce_primary_target_text(step_dict: dict[str, Any]) -> str:
    # Replicate primary_target() logic using dictionary access
    targets = step_dict.get("targets", [])
    primary_target = targets[0] if targets and isinstance(targets, list) else {}
    target_file = primary_target.get("file")
    export_sig = primary_target.get("export")

    if target_file and export_sig:
        return f"{target_file} :: {export_sig}"
    if target_file:
        return target_file
    return ""


async def llm_unified_diff(step_dict: dict[str, Any], variant: str = "base") -> str | None:
    """
    Generate a unified diff via the central PromptSpec orchestrator.
    Output should be raw text starting with '--- a/...'.
    """
    few_shot_example = (
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def main():\n"
        '-    print("hello")\n'
        '+    print("hello, world")\n'
    )

    objective_dict = step_dict.get("objective", {})
    objective_text = (
        objective_dict if isinstance(objective_dict, str) else json.dumps(objective_dict)
    )
    primary_target_text = _coerce_primary_target_text(step_dict)
    context_str = await _targets_context(step_dict)

    prompt_response = await build_prompt(
        scope="simula.codegen.unified_diff",
        summary="Produce a valid unified diff for Simula code evolution",
        context={
            "vars": {
                "objective_text": objective_text,
                "primary_target_text": primary_target_text,
                "file_context": context_str,
                "few_shot_example": few_shot_example,
                "variant": variant,
            },
        },
    )

    try:
        llm_resp = await call_llm_service(
            prompt_response=prompt_response,
            agent_name="Simula",
            scope="simula.codegen.unified_diff",
        )
        raw_text = (getattr(llm_resp, "text", "") or "").strip()

        # Debug (optional)
        print("\n[DEBUG LLM_PATCH] --- RAW LLM Response ---")
        print(raw_text[:2000])
        print("---------------------------------------\n")

        cleaned = _strip_fences(raw_text) or raw_text
        return cleaned if cleaned.startswith("--- a/") else cleaned
    except Exception as e:
        print(f"[PROMPT_PATCH_ERROR] Unexpected error: {e}")
        return None
