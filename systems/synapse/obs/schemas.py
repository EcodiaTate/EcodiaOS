# systems/synapse/obs/schemas.py
# NEW FILE
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GlobalStats(BaseModel):
    """Aggregate statistics for the entire Synapse system."""

    total_episodes: int
    total_arms: int
    active_niches: int
    reward_per_dollar_p50: float
    firewall_blocks_total: int
    genesis_mints_total: int
    genesis_prunes_total: int


class NicheData(BaseModel):
    """Represents a single cell in the QD archive."""

    niche: tuple[str, ...]
    champion_arm_id: str
    score: float
    fitness_share: float


class QDCoverage(BaseModel):
    """The state of the Quality-Diversity archive."""

    coverage_percentage: float
    niches: list[NicheData]


class ROITrend(BaseModel):
    """Time-series data for a single policy arm's ROI."""

    arm_id: str
    roi_history: list[tuple[str, float]]  # List of (timestamp, roi)


class ROITrends(BaseModel):
    """ROI trends for the best and worst performing arms."""

    top_performers: list[ROITrend]
    worst_performers: list[ROITrend]


class EpisodeTrace(BaseModel):
    """A complete, reconstructed trace of a single cognitive decision."""

    episode_id: str
    request_context: dict[str, Any]
    ood_check: dict[str, Any]
    cognitive_strategy: dict[str, Any]
    bandit_scores: dict[str, float]
    critic_reranked_champion: str
    final_economic_scores: dict[str, float]
    simulation_prediction: dict[str, Any]
    firewall_verdict: dict[str, Any]
    final_champion_id: str
    outcome_metrics: dict[str, Any]
    reward_scalar: float
    reward_vector: list[float]
    explanation: dict[str, Any]
    rcu_snapshot: dict[str, str]
