# file: core/telemetry/binders.py
from __future__ import annotations

import os
from typing import Any

from core.telemetry.context import bind_episode, get_ctx

NET_TELEMETRY = os.getenv("ECODIAOS_NET_TELEMETRY", "1") not in ("0", "", "false", "False", "FALSE")


def _dig(d: dict[str, Any] | None, *keys, default=None):
    cur = d or {}
    for k in keys:
        if cur is None:
            return default
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def _coalesce(d: dict[str, Any], *paths, default=None):
    for p in paths:
        if isinstance(p, str):
            val = d.get(p)
            if val is not None:
                return val
        elif isinstance(p, list | tuple):
            val = _dig(d, *p)
            if val is not None:
                return val
    return default


def bind_from_select_arm(task_ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    """
    Central binder: extracts episode + correlation fields from any select_arm shape,
    binds the TelemetryContext once, and seeds correlation so the httpx hooks
    auto-inject headers on all subsequent outbound calls.
    Safe no-op if telemetry disabled.
    """
    if not NET_TELEMETRY:
        return

    # episode id (robust across shapes)
    ep = _coalesce(payload, "episode_id", "episodeId", ["episode", "id"], ["episode", "episode_id"])
    if not ep:
        return  # nothing to bind; bail safely

    task_key = task_ctx.get("task_key") or task_ctx.get("key") or task_ctx.get("name") or "unknown"

    # Bind context
    bind_episode(str(ep), task_key=str(task_key), enabled=True)

    # Correlation seeds (best-effort)
    corr = {
        "decision_id": _coalesce(
            payload,
            "decision_id",
            "decisionId",
            ["correlation", "decision_id"],
        ),
        "spec_id": _coalesce(payload, "spec_id", "specId", ["correlation", "spec_id"]),
        "spec_version": _coalesce(
            payload,
            "spec_version",
            "specVersion",
            ["correlation", "spec_version"],
        ),
        "arm_id": _coalesce(
            payload,
            "arm_id",
            "armId",
            ["champion_arm", "arm_id"],
            ["championArm", "armId"],
            ["champion", "arm_id"],
            ["champion", "id"],
        ),
        "budget_ms": (
            task_ctx.get("budget_ms")
            or task_ctx.get("budgetMs")
            or _coalesce(payload, "budget_ms", "budgetMs", ["correlation", "budget_ms"])
        ),
    }
    # Derive allocated_ms from budget if provided (kept in correlation.* for series)
    alloc = task_ctx.get("allocated_ms") or task_ctx.get("allocatedMs") or corr.get("budget_ms")
    # Remove Nones
    corr = {k: v for k, v in corr.items() if v is not None}

    # Merge into ctx.correlation (non-destructive)
    if corr:
        get_ctx().correlation.update(corr)
    if alloc is not None:
        get_ctx().correlation["allocated_ms"] = alloc
