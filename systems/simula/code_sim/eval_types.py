# systems/simula/code_sim/eval_types.py
"""
Defines the canonical data structures for evaluation results (EvalResult)
and the logic for aggregating those results into a single score (RewardAggregator).
This is the V2 reward system, which integrates with telemetry and is designed
to be configurable and extensible.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

# Attempt to import telemetry; it's a soft dependency for logging rewards.
try:
    from systems.simula.code_sim.telemetry import telemetry
except ImportError:
    # Create a mock telemetry object if it's not available in the context.
    class MockTelemetry:
        def reward(self, *args, **kwargs):
            pass  # No-op

    telemetry = MockTelemetry()

# =========================
# Evaluation Data Structure
# =========================


@dataclass
class EvalResult:
    """A unified, typed container for all evaluator outputs."""

    # Primary pass ratios / scores, scaled to [0,1]
    unit_pass_ratio: float = 0.0
    integration_pass_ratio: float = 0.0
    static_score: float = 0.0
    contracts_score: float = 0.0
    perf_score: float = 0.0
    coverage_delta_score: float = 0.0
    security_score: float = 0.0

    # Optional penalty to be subtracted from the final score
    policy_penalty: float = 0.0  # [0,1] amount to subtract

    # Configurable thresholds for what constitutes a "pass" for hard gates.
    gate_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "unit": 0.99,  # Require all or nearly all unit tests to pass
            "contracts": 0.99,  # Require all contracts to be met
            "security": 0.99,  # Require no high-severity security issues
        },
    )

    def as_dict(self) -> dict:
        """Returns the evaluation result as a dictionary."""
        return asdict(self)

    @property
    def hard_gates_ok(self) -> bool:
        """
        Computes whether the results pass the non-negotiable quality gates.
        Treats missing metrics as 0.0 for this calculation.
        """
        return (
            self.unit_pass_ratio >= self.gate_thresholds.get("unit", 1.0)
            and self.contracts_score >= self.gate_thresholds.get("contracts", 1.0)
            and self.security_score >= self.gate_thresholds.get("security", 1.0)
        )


# =========================
# Reward Aggregation Logic
# =========================

DEFAULT_WEIGHTS: dict[str, float] = {
    "unit": 0.40,
    "integration": 0.15,
    "static": 0.10,
    "contracts": 0.15,
    "perf": 0.10,
    "coverage": 0.05,
    "security": 0.05,
}

# Optional calibration functions can be defined to reshape metric scores.
# Example: lambda x: 1 / (1 + exp(-10 * (x - 0.85)))
CalibFn = Callable[[float], float]
CALIBRATORS: dict[str, CalibFn] = {}


class RewardAggregator:
    """
    Calculates a single [0,1] reward score from a complex EvalResult object.
    Enforces hard gates, applies configurable weights, and handles penalties.
    """

    def __init__(self, cfg: dict[str, Any] | None = None):
        cfg = cfg or {}
        w = cfg.get("weights", {})
        self.weights: dict[str, float] = {**DEFAULT_WEIGHTS, **w}

        # Normalize weights to ensure they sum to 1.0
        total_weight = sum(self.weights.values())
        if total_weight <= 0:
            raise ValueError("Total reward weights must be > 0")
        for k in self.weights:
            self.weights[k] /= total_weight

    def _calibrate(self, name: str, value: float) -> float:
        """Applies a calibration function to a metric if one is defined."""
        calibration_fn = CALIBRATORS.get(name)
        value = max(0.0, min(1.0, float(value)))  # Clamp input
        if not calibration_fn:
            return value
        try:
            # Apply and re-clamp the output
            return max(0.0, min(1.0, float(calibration_fn(value))))
        except Exception:
            return value

    def score(self, eval_result: EvalResult) -> float:
        """
        Computes the final reward score. Returns 0.0 if hard gates fail.
        Otherwise, returns the weighted, calibrated, and penalized score.
        """
        # 1. Check hard gates first
        if not eval_result.hard_gates_ok:
            telemetry.reward(0.0, reason="hard_gates_fail", meta=self.explain(eval_result))
            return 0.0

        # 2. Calculate the weighted sum of calibrated metrics
        weighted_sum = sum(
            self.weights.get(metric, 0.0)
            * self._calibrate(
                metric,
                getattr(
                    eval_result,
                    f"{metric}_score",
                    getattr(eval_result, f"{metric}_pass_ratio", 0.0),
                ),
            )
            for metric in self.weights
        )

        # 3. Apply penalties
        penalized_score = max(0.0, weighted_sum - eval_result.policy_penalty)

        final_score = max(0.0, min(1.0, penalized_score))  # Final clamp
        telemetry.reward(final_score, reason="aggregate_score")
        return final_score

    def explain(self, eval_result: EvalResult) -> dict[str, float]:
        """Returns a dictionary showing the contribution of each metric to the score."""
        contributions = {
            metric: self.weights.get(metric, 0.0)
            * self._calibrate(
                metric,
                getattr(
                    eval_result,
                    f"{metric}_score",
                    getattr(eval_result, f"{metric}_pass_ratio", 0.0),
                ),
            )
            for metric in self.weights
        }
        contributions["penalty"] = -eval_result.policy_penalty
        return contributions
