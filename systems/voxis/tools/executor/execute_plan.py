# systems/voxis/executor/execute_plan.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

# Metrics are optional; we'll no-op if unavailable
try:
    from core.metrics.registry import REGISTRY  # type: ignore
except Exception:
    REGISTRY = None  # type: ignore

from systems.axon.dependencies import get_driver_registry

_log = logging.getLogger("voxis.executor")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _metric_inc(name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
    """Increment a counter/gauge if the metrics registry is available."""
    if REGISTRY is None:
        return
    try:
        REGISTRY.metric(name).labels(**(labels or {})).inc(value)  # type: ignore
    except Exception:
        # Metrics must never break execution.
        pass


def _merge_defaults(params: dict[str, Any], defaults: dict[str, Any] | None) -> dict[str, Any]:
    """Shallow-merge default params into explicit params (explicit wins)."""
    out = dict(defaults or {})
    out.update(params or {})
    return out


def _resolve_tool(step: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """
    Resolve driver/endpoint/params for a tool call.
    Supports both namespaced tool_name ("driver.endpoint") and legacy probe via _meta.
    """
    tool_name = step.get("tool_name") or step.get("function") or step.get("name") or ""
    driver_name: str | None = None
    endpoint: str | None = None

    if "." in tool_name:
        driver_name, endpoint = tool_name.split(".", 1)
    else:
        meta = step.get("_meta", {}) or {}
        driver_name = meta.get("driver_name")
        endpoint = meta.get("endpoint") or step.get("action_type") or "probe"

    if not driver_name or not endpoint:
        raise ValueError(f"Tool call missing driver/endpoint: {step!r}")

    raw_params = step.get("parameters") or {}
    defaults = (step.get("_meta", {}) or {}).get("defaults") or {}
    params = _merge_defaults(raw_params, defaults)

    return driver_name, endpoint, params


async def _exec_tool_call(step: dict[str, Any], ctx: dict[str, Any]) -> Any:
    """
    Execute a single tool step against the Axon driver registry.
    Records results into ctx['tools_results'] for downstream stages.
    """
    driver_name, endpoint, params = _resolve_tool(step)

    registry = get_driver_registry()
    driver = registry.get(driver_name)
    if not driver:
        _metric_inc(
            "tools_call_total",
            {"driver": driver_name, "endpoint": endpoint, "status": "driver_missing"},
        )
        raise RuntimeError(f"Driver '{driver_name}' not found in registry")

    if not hasattr(driver, endpoint):
        _metric_inc(
            "tools_call_total",
            {"driver": driver_name, "endpoint": endpoint, "status": "endpoint_missing"},
        )
        raise RuntimeError(f"Driver '{driver_name}' has no endpoint '{endpoint}'")

    _log.info(
        f"[Executor] tool.call driver='{driver_name}' endpoint='{endpoint}' params_keys={list(params.keys())}"
    )
    try:
        # Endpoint is expected to be an async callable on the driver
        coro = getattr(driver, endpoint)
        result = await coro(params)
        _metric_inc(
            "tools_call_total", {"driver": driver_name, "endpoint": endpoint, "status": "ok"}
        )
    except asyncio.CancelledError:
        _metric_inc(
            "tools_call_total", {"driver": driver_name, "endpoint": endpoint, "status": "cancelled"}
        )
        raise
    except Exception as e:
        _metric_inc(
            "tools_call_total", {"driver": driver_name, "endpoint": endpoint, "status": "error"}
        )
        _log.exception(
            f"[Executor] tool.call failed driver='{driver_name}' endpoint='{endpoint}': {e}"
        )
        raise

    # Persist into context for synthesis/next steps
    ctx.setdefault("tools_results", []).append(
        {
            "driver": driver_name,
            "endpoint": endpoint,
            "params": params,
            "result": result,
        }
    )
    return result


# Optional: simple handlers you can expand later without crashing the pipeline
async def _exec_noop(_: dict[str, Any], __: dict[str, Any]) -> None:
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


async def execute_step(step: dict[str, Any], ctx: dict[str, Any]) -> Any:
    """
    Execute a single plan step. Supports:
      - action_type in {"tool.call", "tool", "probe"}  -> Axon tool call
      - action_type in {"noop", ""}                    -> no-op
    """
    action = (step.get("action_type") or "").lower().strip()

    # Allow legacy "probe" and modern "tool.call"
    if action in ("tool.call", "tool", "probe"):
        return await _exec_tool_call(step, ctx)

    # Graceful fallback for empty/unknown actions
    if action in ("noop", ""):
        _log.debug("[Executor] noop step")
        return await _exec_noop(step, ctx)

    # If you add more actions (say, set_context/sleep/etc.), route here:
    # if action == "set_context": ...
    # if action == "sleep": ...

    raise RuntimeError(f"Unknown action_type='{action}'")


async def execute_plan(
    plan: list[dict[str, Any]], ctx: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Execute a list of plan steps sequentially.
    Returns the (possibly augmented) ctx, including:
      - ctx['tools_results']: list of tool call transcripts
      - ctx['step_results']: raw results per step index (best-effort)
      - ctx['errors']: list of error dicts (if any step fails)
    """
    ctx = ctx or {}
    ctx.setdefault("tools_results", [])
    ctx.setdefault("step_results", [])
    ctx.setdefault("errors", [])

    if not isinstance(plan, list):
        raise ValueError("execute_plan expects 'plan' to be a list of step dicts")

    for idx, step in enumerate(plan):
        try:
            result = await execute_step(step, ctx)
            ctx["step_results"].append({"index": idx, "status": "ok", "result": result})
        except Exception as e:
            _log.exception(f"[Executor] Step {idx} failed: {e}")
            ctx["errors"].append({"index": idx, "error": str(e), "step": step})
            ctx["step_results"].append({"index": idx, "status": "error", "error": str(e)})
            # Policy choice: continue or break. We continue so synthesis can still run with partial data.
            # break

    return ctx
