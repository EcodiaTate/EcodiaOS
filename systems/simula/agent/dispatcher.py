# systems/simula/agent/dispatcher.py
# --- UNIFIED TOOL DISPATCHER FOR SIMULA (Upgraded) ---

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from typing import Any, Dict, Tuple

from systems.simula.code_sim.telemetry import get_tracked_tools

log = logging.getLogger(__name__)

# Load tool registry (each entry: {"func": <callable>, ...meta})
TOOL_MAP: dict[str, dict[str, Any]] = get_tracked_tools()
_SIMULA_PREFIX = "simula.agent."

# Sensible defaults (env-overridable)
DEFAULT_TIMEOUT_S = float(os.getenv("SIMULA_TOOL_TIMEOUT_S", "30.0"))
DEFAULT_MAX_OUTPUT_CHARS = int(os.getenv("SIMULA_TOOL_MAX_OUTPUT_CHARS", "20000"))
DEFAULT_MAX_ITEMS = int(os.getenv("SIMULA_TOOL_MAX_ITEMS", "200"))
SANDBOX_ROOT = os.getenv("SANDBOX_ROOT", "/app")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _short(obj: Any, limit: int = 600) -> str:
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return (s[:limit] + "…") if len(s) > limit else s


def _resolve_tool_from_arm_id(arm_id: str) -> str | None:
    """
    Accepts ids like:
      - "simula.agent.run_tests"
      - "simula.agent.run_tests.v1"
      - "run_tests"
    Returns the TOOL_MAP key (e.g., "run_tests") if resolvable.
    """
    if arm_id in TOOL_MAP:
        return arm_id
    if arm_id.startswith(_SIMULA_PREFIX):
        tail = arm_id[len(_SIMULA_PREFIX) :]
        base = tail.split(".", 1)[0]
        if base in TOOL_MAP:
            return base
    # final direct check (already covered, but keep for clarity)
    return arm_id if arm_id in TOOL_MAP else None


def _coerce_params_for_signature(
    fn: Any, params: dict[str, Any], *, strict: bool,
) -> tuple[dict[str, Any], list]:
    """
    - Drops unknown kwargs when strict=False, records them in 'dropped'.
    - When strict=True, raises on unknown kwargs.
    - Leaves type coercion to the tool itself (avoid over-magic).
    """
    try:
        sig = inspect.signature(fn)
    except Exception:
        # If we can't introspect, pass as-is (best effort).
        return dict(params or {}), []

    allowed = set(sig.parameters.keys())
    params = dict(params or {})
    dropped = [k for k in list(params.keys()) if k not in allowed]

    if dropped and strict:
        raise TypeError(f"Unknown parameter(s): {dropped}")

    for k in dropped:
        params.pop(k, None)

    return params, dropped


def _resolve_paths(params: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve relative sandbox paths conservatively. Only touch strings that
    look like paths (contain '/' or end with common file suffixes).
    """

    def _fix(v: Any) -> Any:
        if isinstance(v, str):
            if v.startswith(SANDBOX_ROOT) or v.startswith("/") or "://" in v:
                return v
            if ("/" in v) or v.endswith((".py", ".txt", ".md", ".json", ".yaml", ".yml")):
                return os.path.join(SANDBOX_ROOT, v.lstrip("/"))
            return v
        if isinstance(v, list):
            return [_fix(x) for x in v]
        if isinstance(v, dict):
            return {k: _fix(x) for k, x in v.items()}
        return v

    return {k: _fix(v) for k, v in (params or {}).items()}


def _truncate(obj: Any, *, max_chars: int, max_items: int) -> tuple[Any, bool]:
    """
    Truncate large outputs without losing structure.
    - strings: cut to max_chars
    - lists/tuples: cap to max_items and recursively truncate items
    - dicts: keep all keys but truncate string values and cap large lists
    """
    truncated = False

    if isinstance(obj, str):
        if len(obj) > max_chars:
            return obj[:max_chars] + "…", True
        return obj, False

    if isinstance(obj, (list, tuple)):
        seq = list(obj)
        if len(seq) > max_items:
            seq = seq[:max_items]
            truncated = True
        out = []
        for it in seq:
            v, t = _truncate(it, max_chars=max_chars, max_items=max_items)
            out.append(v)
            truncated = truncated or t
        return out, truncated

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            vv, t = _truncate(v, max_chars=max_chars, max_items=max_items)
            out[k] = vv
            truncated = truncated or t
        return out, truncated

    # numbers, bools, None, or unknown objects → best-effort repr then cut
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    if len(s) > max_chars:
        return s[:max_chars] + "…", True
    return obj, False


def _build_evidence_card(tool_key: str, outcome: dict[str, Any]) -> dict[str, Any]:
    """
    Compact, transport-safe evidence descriptor:
      - Never includes raw large blobs.
      - Meant for UI & prompt summaries (not full context).
    """
    status = (outcome.get("status") or "").lower()
    preview = outcome.get("preview") or outcome.get("summary") or outcome.get("reason") or ""
    data = outcome.get("data")
    size_hint = None
    try:
        if isinstance(data, str):
            size_hint = len(data)
        elif isinstance(data, (list, tuple, dict)):
            size_hint = len(json.dumps(data, ensure_ascii=False))
    except Exception:
        size_hint = None

    return {
        "type": "tool_result",
        "tool": tool_key,
        "status": status,
        "preview": _short(preview, 240),
        "size_hint": size_hint,
        "meta": {
            "had_truncation": bool(outcome.get("metrics", {}).get("truncated")),
            "duration_ms": outcome.get("metrics", {}).get("duration_ms"),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────────


async def dispatch_tool(arm_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve and run a registered tool with:
      • strict allowlist via orchestrator (enforced there; we still validate existence here)
      • param sanitization (drop unknowns unless strict=True in tool meta)
      • optional path resolution (tool meta: resolve_paths=True)
      • timeout (tool meta: timeout_s)
      • safe truncation of outputs (env defaults or tool meta)
      • normalized result schema

    Normalized return shape:
    {
      "status": "success" | "error",
      "reason": "...",              # on error
      "data": <any>,                # truncated by policy
      "preview": "short human blurb (optional)",
      "evidence": [ { evidence_card }, ... ],
      "metrics": {
        "duration_ms": int,
        "truncated": bool,
        "timeout": bool
      },
      "tool_info": {
        "name": "run_tests",
        "version": "v1",
        "timeout_s": 30.0
      }
    }
    """
    tool_key = _resolve_tool_from_arm_id(arm_id)
    if not tool_key or tool_key not in TOOL_MAP:
        log.error("Unknown tool for arm_id '%s'. Registry has: %s", arm_id, list(TOOL_MAP.keys()))
        return {
            "status": "error",
            "reason": f"Tool '{tool_key or arm_id}' not found in registry.",
            "metrics": {"duration_ms": 0, "truncated": False, "timeout": False},
            "tool_info": {"name": tool_key or arm_id, "version": None, "timeout_s": None},
        }

    meta = TOOL_MAP[tool_key] or {}
    tool_fn = meta.get("func")
    if not callable(tool_fn):
        log.error("Tool '%s' resolved but its 'func' attribute is not callable.", tool_key)
        return {
            "status": "error",
            "reason": f"Tool '{tool_key}' is not configured correctly.",
            "metrics": {"duration_ms": 0, "truncated": False, "timeout": False},
            "tool_info": {"name": tool_key, "version": meta.get("version"), "timeout_s": None},
        }

    # Meta policy
    timeout_s = float(meta.get("timeout_s", DEFAULT_TIMEOUT_S))
    strict_params = bool(meta.get("strict_params", False))
    resolve_paths = bool(meta.get("resolve_paths", True))
    max_chars = int(meta.get("max_output_chars", DEFAULT_MAX_OUTPUT_CHARS))
    max_items = int(meta.get("max_items", DEFAULT_MAX_ITEMS))

    # Param shaping
    try:
        shaped_params, dropped = _coerce_params_for_signature(
            tool_fn, params or {}, strict=strict_params,
        )
        if resolve_paths:
            shaped_params = _resolve_paths(shaped_params)
        if dropped:
            log.debug("[Dispatcher] Dropped unknown args for '%s': %s", tool_key, dropped)
    except Exception as e:
        return {
            "status": "error",
            "reason": f"Parameter validation failed for '{tool_key}': {e}",
            "metrics": {"duration_ms": 0, "truncated": False, "timeout": False},
            "tool_info": {"name": tool_key, "version": meta.get("version"), "timeout_s": timeout_s},
        }

    # Execute with timeout
    start = asyncio.get_event_loop().time()
    timeout_hit = False
    raw_result: dict[str, Any] | Any

    log.info(
        "[Dispatcher] ▶ tool | tool=%s timeout=%.1fs params=%s",
        tool_key,
        timeout_s,
        _short(shaped_params, 400),
    )

    try:
        raw_result = await asyncio.wait_for(tool_fn(**shaped_params), timeout=timeout_s)
    except TimeoutError:
        timeout_hit = True
        log.error("[Dispatcher] ⏱ timeout | tool=%s after %.1fs", tool_key, timeout_s)
        duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
        return {
            "status": "error",
            "reason": f"Tool '{tool_key}' timed out after {timeout_s:.1f}s.",
            "metrics": {"duration_ms": duration_ms, "truncated": False, "timeout": True},
            "tool_info": {"name": tool_key, "version": meta.get("version"), "timeout_s": timeout_s},
        }
    except Exception as e:
        log.exception("[Dispatcher] crash | tool=%s", tool_key)
        duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
        return {
            "status": "error",
            "reason": f"Tool '{tool_key}' crashed: {e!r}",
            "metrics": {"duration_ms": duration_ms, "truncated": False, "timeout": False},
            "tool_info": {"name": tool_key, "version": meta.get("version"), "timeout_s": timeout_s},
        }

    duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)

    # Normalize arbitrary tool outputs into our envelope
    if isinstance(raw_result, dict) and "status" in raw_result:
        # Tool already returned a structured envelope (preferred pattern)
        status = (raw_result.get("status") or "").lower()
        data = raw_result.get("data")
        preview = raw_result.get("preview") or raw_result.get("summary")
        truncated = False

        if data is not None:
            data, t = _truncate(data, max_chars=max_chars, max_items=max_items)
            truncated = truncated or t

        # Build evidence card if not provided
        evidence = raw_result.get("evidence")
        if not evidence:
            evidence = [
                _build_evidence_card(
                    tool_key,
                    {
                        "status": status,
                        "preview": preview,
                        "data": data,
                        "metrics": {"duration_ms": duration_ms, "truncated": truncated},
                    },
                ),
            ]

        result = {
            "status": status if status in ("success", "ok") else ("error" if status else "success"),
            "reason": raw_result.get("reason"),
            "data": data,
            "preview": preview or (raw_result.get("reason") if status != "success" else None),
            "evidence": evidence,
            "metrics": {
                "duration_ms": duration_ms,
                "truncated": truncated or bool(raw_result.get("metrics", {}).get("truncated")),
                "timeout": timeout_hit or bool(raw_result.get("metrics", {}).get("timeout")),
            },
            "tool_info": {
                "name": tool_key,
                "version": meta.get("version"),
                "timeout_s": timeout_s,
            },
        }
        log.info(
            "[Dispatcher] ◀ tool | tool=%s status=%s ms=%d truncated=%s",
            tool_key,
            result["status"],
            duration_ms,
            result["metrics"]["truncated"],
        )
        return result

    # Otherwise, wrap raw value
    data, truncated = _truncate(raw_result, max_chars=max_chars, max_items=max_items)
    result = {
        "status": "success",
        "data": data,
        "preview": None,
        "evidence": [
            _build_evidence_card(
                tool_key,
                {
                    "status": "success",
                    "data": data,
                    "metrics": {"duration_ms": duration_ms, "truncated": truncated},
                },
            ),
        ],
        "metrics": {"duration_ms": duration_ms, "truncated": truncated, "timeout": False},
        "tool_info": {"name": tool_key, "version": meta.get("version"), "timeout_s": timeout_s},
    }
    log.info(
        "[Dispatcher] ◀ tool | tool=%s status=success ms=%d truncated=%s",
        tool_key,
        duration_ms,
        truncated,
    )
    return result
