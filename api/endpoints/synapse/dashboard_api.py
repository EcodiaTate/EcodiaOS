# systems/synapse/api/endpoints/dashboard_api.py
# LIVE OBSERVABILITY ENDPOINTS (no stubs)
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.obs.queries import (
    get_full_episode_trace,
    get_global_stats,
    get_qd_coverage_data,
)
from systems.synapse.obs.schemas import (
    EpisodeTrace,
    GlobalStats,
    QDCoverage,
    ROITrends,
)

dashboard_router = APIRouter(prefix="/obs", tags=["Synapse Observability"])


@dashboard_router.get("/global_stats", response_model=GlobalStats)
async def get_stats():
    """Returns high-level aggregate statistics about the system's health."""
    stats = await get_global_stats()
    return GlobalStats(**stats)


@dashboard_router.get("/qd_coverage", response_model=QDCoverage)
async def get_qd_coverage():
    """Returns the current state of the Quality-Diversity archive."""
    coverage_data = await get_qd_coverage_data()
    return QDCoverage(**coverage_data)


@dashboard_router.get("/roi_trends", response_model=ROITrends)
async def get_roi_trends(
    days: int = Query(30, ge=1, le=365, description="Lookback window (days)"),
    top_k: int = Query(3, ge=1, le=10, description="Series per bucket (top & bottom)"),
    rank_window_days: int = Query(
        7,
        ge=1,
        le=90,
        description="Ranking window for top/bottom selection",
    ),
):
    """
    Returns time-series ROI data for top and bottom performing arms.

    - Pulls per-day average ROI per arm across the `days` lookback.
    - Ranks arms by average ROI over the most recent `rank_window_days`.
    - Returns `top_k` series for the best and worst arms, with daily points.
    """
    try:
        # 1) Pull daily series from the graph (defensive over field names).
        # Fields tolerated:
        #   ROI: e.roi, e.reward, e.return, e.score (first non-null)
        #   Time: e.ended_at, e.created_at, e.started_at (first non-null)
        rows = await cypher_query(
            """
            MATCH (e:Episode)-[:USED_ARM]->(a:Arm)
            WITH e, a,
                 coalesce(e.roi, e.reward, e.return, e.score) AS roi,
                 coalesce(e.ended_at, e.created_at, e.started_at) AS t
            WHERE roi IS NOT NULL AND t IS NOT NULL
              AND t >= datetime() - duration({days: $days})
            WITH a.id AS arm_id, date(t) AS d, roi
            RETURN arm_id, d AS day, avg(roi) AS avg_roi
            ORDER BY day ASC
            """,
            {"days": days},
        )
        if not rows:
            # Provide a valid, but empty trends object
            return ROITrends(
                window_days=days,
                top=[],
                bottom=[],
                metadata={"rank_window_days": rank_window_days},
            )

        # 2) Group by arm → build time series (list of (day, roi))
        series_by_arm: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for r in rows:
            arm_id = r.get("arm_id")
            day = r.get("day")
            avg_roi = r.get("avg_roi")
            if not arm_id or day is None or avg_roi is None:
                continue
            # Neo4j date → datetime (UTC midnight for consistency)
            dt_day = datetime(day.year, day.month, day.day, tzinfo=UTC)
            series_by_arm[arm_id].append((dt_day, float(avg_roi)))

        # 3) For ranking, compute average ROI over the last `rank_window_days`
        now = datetime.now(UTC)
        rank_cut = now - timedelta(days=rank_window_days)
        ranking: list[tuple[str, float]] = []
        for arm_id, points in series_by_arm.items():
            recent = [roi for (t, roi) in points if t >= rank_cut]
            if not recent:
                continue
            ranking.append((arm_id, sum(recent) / len(recent)))
        if not ranking:
            # Fall back to overall mean if no points in rank window
            for arm_id, points in series_by_arm.items():
                vals = [roi for (_, roi) in points]
                if vals:
                    ranking.append((arm_id, sum(vals) / len(vals)))

        if not ranking:
            return ROITrends(
                window_days=days,
                top=[],
                bottom=[],
                metadata={"rank_window_days": rank_window_days},
            )

        ranking.sort(key=lambda x: x[1])  # ascending by ROI
        bottom_ids = [arm for (arm, _) in ranking[:top_k]]
        top_ids = [arm for (arm, _) in ranking[-top_k:]][::-1]  # best first

        # 4) Normalize each series to contiguous daily points across the window
        #    (missing days omitted; UI can resample if desired).
        def pack(arm_id: str) -> dict[str, Any]:
            pts = series_by_arm.get(arm_id, [])
            pts.sort(key=lambda x: x[0])
            return {
                "arm_id": arm_id,
                "points": [{"t": p[0].date().isoformat(), "roi": p[1]} for p in pts],
            }

        top_series = [pack(a) for a in top_ids]
        bottom_series = [pack(a) for a in bottom_ids]

        return ROITrends(
            window_days=days,
            top_performers=top_series,
            worst_performers=bottom_series,
            metadata={
                "rank_window_days": rank_window_days,
                "top_ids": top_ids,
                "bottom_ids": bottom_ids,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ROI trend query failed: {e}") from e


@dashboard_router.get("/episode/{episode_id}", response_model=EpisodeTrace)
async def get_episode(episode_id: str):
    """Retrieves the full, detailed trace for a single decision episode."""
    trace = await get_full_episode_trace(episode_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Episode not found.")
    return EpisodeTrace(**trace)


@dashboard_router.get("/outcomes")
async def get_outcomes_data():
    """
    Loads outcomes.json from disk and returns a normalized subset
    for visualization purposes.
    """
    path = Path("./data/synapse/outcomes.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="outcomes.json not found")

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    def parse_arm_id(arm_id: str):
        parts = arm_id.split(".")
        return {
            "strategy": parts[1] if len(parts) > 1 else None,
            "model": parts[3] if len(parts) > 3 else None,
            "tokenizer": parts[4] if len(parts) > 4 else None,
        }

    # Normalize fields
    results = []
    for row in raw:
        meta = parse_arm_id(row["arm_id"])
        results.append(
            {
                "timestamp": row["timestamp"],
                "episode_id": row["episode_id"],
                "task_key": row["task_key"],
                "arm_id": row["arm_id"],
                "strategy": meta["strategy"],
                "model": meta["model"],
                "tokenizer": meta["tokenizer"],
                "scalar_reward": row["scalar_reward"],
                "reward_vector": row["reward_vector"],
                "success": row["metrics"].get("success"),
                "utility_score": row["metrics"].get("utility_score"),
                "reasoning": row["metrics"].get("reasoning"),
            },
        )

    return JSONResponse(content=results)
