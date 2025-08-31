# systems/atune/planner/fae.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FAEScore:
    final_score: float
    terms: dict[str, float]


class FAE_Calculator:
    """
    FAE = U + λ_IG·IG − λ_R·Risk − λ_C·Cost
    - U: utility proxy from salience (sum of gated final scores)
    - IG: information gain from probes (sum of per-probe ig)
    - Risk: risk proxy from salience risk-head final score
    - Cost: sum of probe cost_ms (milliseconds)
    """

    def __init__(
        self,
        lambda_epi: float = 1.0,
        lambda_risk: float = 1.0,
        lambda_cost: float = 0.001,
    ):
        self.lambda_ig = lambda_epi
        self.lambda_risk = lambda_risk
        self.lambda_cost = lambda_cost

    def calculate_fae(
        self,
        salience_scores: dict[str, Any],
        probe_results: dict[str, Any],
    ) -> FAEScore:
        utility = sum(v.get("final_score", 0.0) for v in salience_scores.values())
        ig = sum(p.get("ig", 0.0) for p in probe_results.values())
        risk = salience_scores.get("risk-head", {}).get("final_score", 0.0)
        cost_ms = sum(p.get("cost_ms", 0.0) for p in probe_results.values())

        score = utility + self.lambda_ig * ig - self.lambda_risk * risk - self.lambda_cost * cost_ms
        return FAEScore(
            final_score=float(score),
            terms={
                "U": float(utility),
                "IG": float(ig),
                "Risk": float(risk),
                "Cost_ms": float(cost_ms),
                "lambda_ig": float(self.lambda_ig),
                "lambda_risk": float(self.lambda_risk),
                "lambda_cost": float(self.lambda_cost),
            },
        )
