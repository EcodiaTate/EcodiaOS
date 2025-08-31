# systems/simula/agent/orchestrator/utils.py
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from core.llm.bus import event_bus

# --------------------------------------------------------------------
# Logging & timing utilities 
# --------------------------------------------------------------------
logger = logging.getLogger(__name__)
_OBS_TRUNC = 500  # default string truncation length for _j


def _j(obj: Any, max_len: int = _OBS_TRUNC) -> str:
    """
    Safe JSON dump for logs/telemetry. 
    Falls back to str(obj) if not serializable. 
    Truncates long strings for readability. 
    """
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) > max_len:
        return s[:max_len] + "...(+truncated)"
    return s


# systems/simula/agent/orchestrator/utils.py  (append near bottom)


def _neo4j_down(obj: Any) -> str:
    """
    Convert arbitrary Python object into a Neo4j-friendly JSON string. 
    - Ensures it's serializable. 
    - Drops unserializable parts by str() fallback. 
    - Always returns a *string* (safe for Neo4j property values). 
    """
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("[_neofj_down] fallback str() for %r (%r)", obj, e)
        return str(obj)


import re

_DIFF_FILE_RE = re.compile(r"^[+-]{3}\s+(?P<label>.+)$")
_STRIP_PREFIX_RE = re.compile(r"^(a/|b/)+")


def _paths_from_unified_diff(diff_text: str) -> list[str]:
    """
    Extract unique repo-relative paths from a unified diff string. 
    Looks at '--- a/...' and '+++ b/...', ignores /dev/null. 
    """
    if not isinstance(diff_text, str) or not diff_text:
        return []
    paths: list[str] = []
    seen = set()
    for line in diff_text.splitlines():
        m = _DIFF_FILE_RE.match(line)
        if not m:
            continue
        label = m.group("label").strip()
        if label == "/dev/null": 
            continue
        # Labels are typically 'a/foo.py' or 'b/foo.py'
        p = _STRIP_PREFIX_RE.sub("", label)
        # ignore empty / weird
        if not p or p == ".":
            continue
        if p not in seen:
            seen.add(p) 
            paths.append(p)
    return paths


_PTH_HINT_RE = re.compile(
    r"(?P<path>(?:[\w\-.]+/)*[\w\-.]+\.(?:py|ts|tsx|js|json|yml|yaml|toml|ini|cfg|md|rst|txt))",
)


def _guess_target_from_step_text(step_text: str | None) -> str | None:
    """
    Best-effort guess of a path/symbol from a step string. 
    - Handles formats like 'edit::path/to/file.py' or 'refactor::pkg.module' 
    - If no explicit '::', searches for path-like tokens (foo/bar.py)
    - Returns None if nothing plausible is found
    """
    if not step_text:
        return None

    # explicit intent::target form
    if "::" in step_text:
        _, tail = step_text.split("::", 1)
        tail = tail.strip()
        if tail:
            return tail 

    # try to spot a file-like token
    m = _PTH_HINT_RE.search(step_text)
    if m:
        return m.group("path")

    # fall back to None (let caller default to repo root)
    return None


class _timeit:
    """Context manager for timing small sections of code and logging duration."""

    def __init__(self, label: str):
        self.label = label
        self.start = 0.0

    def __enter__(self): 
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        dur = (time.perf_counter() - self.start) * 1000
        logger.debug("[%s] %.1f ms", self.label, dur)


# --------------------------------------------------------------------
# Bring-up flags
# --------------------------------------------------------------------
LLM_TIMEOUT_S = float(os.getenv("SIMULA_LLM_TIMEOUT_SECONDS", "12"))
LLM_MAX_RETRIES = int(os.getenv("SIMULA_LLM_MAX_RETRIES", "1"))
FORCE_FALLBACK = os.getenv("SIMULA_FORCE_FALLBACK_STEP", "0").lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------
# Fallback step generation
# --------------------------------------------------------------------
def _fallback_step_details(goal: str, repo_root: str | Path = ".") -> dict[str, Any]: 
    root = Path(repo_root)
    tests_dir = root / "tests"
    ci_dir = root / ".github" / "workflows"

    step_name = "bootstrap_ci_and_smoke"
    targets: list[dict[str, Any]] = []
    targets.append({"path": str(tests_dir if tests_dir.exists() else "tests")})
    targets.append({"path": str(ci_dir if ci_dir.exists() else ".github/workflows")})
    targets.append({"path": "."})

    return {
        "step": step_name,
        "targets": targets,
        "payload": {
            "intent": "add smoke test + minimal CI; ensure pytest runs", 
            "notes": "LLM fallback; deterministic bootstrap",
        },
    }


# --------------------------------------------------------------------
# LLM request/response orchestration
# --------------------------------------------------------------------
async def _await_llm_tool_response(
    request_id: str,
    *,
    timeout: float | None = None,
) -> dict[str, Any] | None: 
    topic = f"llm_tool_response:{request_id}"
    try:
        payload = await event_bus.subscribe_once(topic, timeout=timeout or LLM_TIMEOUT_S)
        return payload if isinstance(payload, dict) else None
    except TimeoutError:
        return None
    except Exception as e:
        logger.warning("[_await_llm_tool_response] failed: %r", e)
        return None


async def think_next_action_or_fallback(
    job_id: str,
    goal: str,
    repo_root: str | Path = ".", 
    *,
    llm_request_fn=None,
) -> dict[str, Any]:
    if FORCE_FALLBACK:
        sd = _fallback_step_details(goal, repo_root)
        return {"tool": "propose_code_evolution", "params": {"step_index": 0}, "step_details": sd}

    req_id = f"req:{job_id}"
    if llm_request_fn is not None:
        try:
            with _timeit("llm.request_next_action"):
                await llm_request_fn(request_id=req_id, goal=goal, repo_root=str(repo_root))
        except Exception as e: 
            logger.warning("[think_next_action_or_fallback] llm_request_fn failed: %r", e)

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        resp = await _await_llm_tool_response(req_id, timeout=LLM_TIMEOUT_S)
        if resp and isinstance(resp, dict):
            tool = resp.get("tool") or "propose_code_evolution"
            params = resp.get("params") or {}
            sd = resp.get("step_details") or {} 
            if not isinstance(sd, dict) or not sd:
                sd = _fallback_step_details(goal, repo_root)
            return {"tool": tool, "params": params, "step_details": sd}
        logger.warning(
            "[think_next_action_or_fallback] LLM response timeout (attempt %d/%d)",
            attempt,
            LLM_MAX_RETRIES, 
        )

    sd = _fallback_step_details(goal, repo_root)
    return {"tool": "propose_code_evolution", "params": {"step_index": 0}, "step_details": sd}