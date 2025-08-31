from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from httpx import HTTPStatusError

from core.prompting.orchestrator import PolicyHint, build_prompt
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


async def _targets_context(step: Any) -> str:
    blocks = []
    targets = getattr(step, "targets", []) or (
        step.get("targets") if isinstance(step, dict) else []
    )
    for t in targets or []:
        rel = getattr(t, "file", None) or (t.get("file") if isinstance(t, dict) else None)
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


def _coerce_primary_target_text(step: Any) -> str:
    # allow callable .primary_target() returning tuple, or plain str/tuple, or dict
    pt = getattr(step, "primary_target", None)
    if callable(pt):
        try:
            pt = pt()
        except Exception:
            pt = None
    if isinstance(pt, tuple):
        return " — ".join(str(x) for x in pt if x)
    if isinstance(pt, dict):
        return json.dumps(pt, ensure_ascii=False)
    if isinstance(pt, str):
        return pt
    return ""


async def llm_unified_diff(step: Any, variant: str = "base") -> str | None:
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

    # Gather context vars safely
    objective_text = getattr(step, "objective", None) or (
        step.get("objective") if isinstance(step, dict) else ""
    )
    primary_target_text = _coerce_primary_target_text(step)
    context_str = await _targets_context(step)

    # Build prompt via PromptSpec (no raw strings)
    hint = PolicyHint(
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
    o = await build_prompt(hint)

    # Call LLM Bus using provider overrides from the spec
    request_payload = {
        "messages": o.messages,
        "json_mode": bool(o.provider_overrides.get("json_mode", False)),  # should be False for text
        "max_tokens": int(o.provider_overrides.get("max_tokens", 700)),
    }
    temp = o.provider_overrides.get("temperature", None)
    if temp is not None:
        request_payload["temperature"] = float(temp)

    try:
        client = await get_http_client()
        resp = await client.post(ENDPOINTS.LLM_CALL, json=request_payload, timeout=120.0)
        resp.raise_for_status()
        llm_response = resp.json()
        raw_text = (llm_response.get("text") or "").strip()

        # Debug (optional)
        print("\n[DEBUG LLM_PATCH] --- RAW LLM Response ---")
        print(raw_text[:2000])
        print("---------------------------------------\n")

        # Defensive cleanup: strip accidental fences/comments
        cleaned = _strip_fences(raw_text) or raw_text
        return cleaned if cleaned.startswith("--- a/") else cleaned
    except HTTPStatusError as e:
        print(
            f"[PROMPT_PATCH_ERROR] LLM Bus returned a server error: {e}\n{getattr(e, 'response', None) and e.response.text}",
        )
        return None
    except Exception as e:
        print(f"[PROMPT_PATCH_ERROR] An unexpected error occurred: {e}")
        return None
