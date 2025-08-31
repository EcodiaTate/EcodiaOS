from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from systems.synapse.obs.queries_budget import get_budget_series
from systems.synapse.obs.queries_metrics import (
    get_agents_overview,
    get_arm_leaderboard,
    get_metric_series,
)
from systems.synapse.obs.schemas_metrics import (
    AgentBadge,
    AgentsOverview,
    MetricPoint,
    MetricSeries,
)

metrics_router = APIRouter(prefix="/metrics", tags=["Synapse Metrics"])


@metrics_router.get("/series", response_model=list[MetricSeries])
async def series(
    name: str = Query(
        ...,
        description='Metric path, e.g. "llm.llm_latency_ms" or "nova.propose_ms"',
    ),
    scope: str | None = Query(None, description="Scope segment if not included in name"),
    system: str | None = Query(None, description="Filter to a system/agent name"),
    days: int = Query(30, ge=1, le=365),
    group_by: str | None = Query(
        None,
        description='One of: "provider"|"model"|"arm_id"|"decision_id"|<metric-tag>',
    ),
) -> list[MetricSeries]:
    try:
        rows = await get_metric_series(
            name,
            scope=scope,
            system=system,
            days=days,
            group_by=group_by,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"metrics series failed: {e}") from e

    series_map: dict[str, MetricSeries] = {}
    for r in rows:
        sys = r.get("system", "")
        tag = r.get("tag", "")
        key = f"{sys}::{tag}"
        ms = series_map.get(key)
        if ms is None:
            ms = MetricSeries(
                name=r.get("name", name),
                system=sys or "",
                scope=r.get("scope", "") or "",
                tags=({"group": group_by, "tag": tag} if group_by else {}),
                points=[],
            )
            series_map[key] = ms
        day = r.get("day")
        val = float(r.get("avg_value", 0.0) or 0.0)
        ms.points.append(MetricPoint(t=str(day), value=val, tags=ms.tags))
    return list(series_map.values())


@metrics_router.get("/agents", response_model=AgentsOverview)
async def agents(days: int = Query(30, ge=1, le=365)) -> AgentsOverview:
    try:
        rows = await get_agents_overview(days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"metrics agents failed: {e}") from e
    badges = [
        AgentBadge(
            **{
                "agent": r.get("agent", "unknown"),
                "calls": int(r.get("calls", 0) or 0),
                "avg_latency_ms": float(r.get("avg_latency_ms", 0.0) or 0.0),
                "p95_latency_ms": float(r.get("p95_latency_ms", 0.0) or 0.0),
                "prompt_tokens": int(r.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(r.get("completion_tokens", 0) or 0),
                "success_rate": float(r.get("success_rate", 0.0) or 0.0),
            },
        )
        for r in rows
    ]
    return AgentsOverview(window_days=days, agents=badges)


@metrics_router.get("/leaderboard")
async def leaderboard(
    days: int = Query(30, ge=1, le=365),
    top_k: int = Query(5, ge=1, le=20),
) -> dict[str, list[dict[str, Any]]]:
    try:
        return await get_arm_leaderboard(days, top_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"metrics leaderboard failed: {e}") from e


@metrics_router.get("/budget", response_model=list[MetricSeries])
async def budget(days: int = Query(30, ge=1, le=365)) -> list[MetricSeries]:
    """
    Returns two series: correlation.allocated_ms and correlation.spent_ms (daily sums).
    """
    try:
        rows = await get_budget_series(days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"metrics budget failed: {e}") from e

    series_map: dict[str, MetricSeries] = {}
    for r in rows:
        name = r.get("name", "")
        ms = series_map.get(name)
        if ms is None:
            ms = MetricSeries(name=name, system="", scope="", tags={}, points=[])
            series_map[name] = ms
        day = r.get("day")
        val = float(r.get("sum_value", 0.0) or 0.0)
        ms.points.append(MetricPoint(t=str(day), value=val, tags={}))
    return list(series_map.values())
