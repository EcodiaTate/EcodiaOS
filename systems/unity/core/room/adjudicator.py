# systems/unity/core/room/adjudicator.py

from typing import Any

import numpy as np

from core.utils.neo.cypher_query import cypher_query
from systems.unity.schemas import VerdictModel


class Adjudicator:
    """
    A rule-aware, fail-closed singleton service that determines the final
    verdict of a deliberation using Bayesian aggregation.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _get_applicable_rules(self, constraints: list[str]) -> list[dict[str, Any]]:
        """Fetches constitutional rules from Equor's data in Neo4j."""
        if not constraints:
            return []
        query = "MATCH (r:ConstitutionRule) WHERE r.id IN $rule_ids RETURN r"
        results = await cypher_query(query, params={"rule_ids": constraints})
        return [res["r"] for res in results] if results else []

    def _bayesian_aggregation(
        self,
        participant_beliefs: dict[str, float],
        calibration_priors: dict[str, float],
    ) -> tuple[float, float]:
        """
        Aggregates participant beliefs using Bayesian model averaging.

        Args:
            participant_beliefs: A dict of {"role": belief_score}, where belief_score is
                                 the participant's confidence in approval [0,1].
            calibration_priors: A dict of {"role": prior}, where prior is the
                                historical reliability of the participant [0,1].

        Returns:
            A tuple of (final_confidence, final_uncertainty).
        """
        if not participant_beliefs:
            return 0.0, 1.0

        log_odds = []
        for role, belief in participant_beliefs.items():
            # Use a default prior if one isn't provided by Synapse
            prior = calibration_priors.get(role, 0.7)

            # Convert belief and prior to log-odds (logit function)
            # Add a small epsilon to avoid division by zero
            epsilon = 1e-9
            belief = np.clip(belief, epsilon, 1 - epsilon)
            prior = np.clip(prior, epsilon, 1 - epsilon)

            # The weight is the log-odds of the prior (how much we trust the source)
            weight = np.log(prior / (1 - prior))

            # The evidence is the log-odds of the belief
            evidence = np.log(belief / (1 - belief))

            log_odds.append(weight * evidence)

        # The combined evidence is the sum of weighted log-odds
        combined_log_odds = np.sum(log_odds)

        # Convert back to probability (logistic function)
        final_confidence = 1 / (1 + np.exp(-combined_log_odds))

        # Uncertainty can be modeled as the variance of the beliefs
        uncertainty = (
            np.var(list(participant_beliefs.values())) if len(participant_beliefs) > 1 else 0.0
        )

        return float(final_confidence), float(uncertainty)

    async def decide(
        self,
        participant_beliefs: dict[str, float],
        calibration_priors: dict[str, float],
        spec_constraints: list[str],
    ) -> VerdictModel:
        """
        Makes a final decision based on beliefs, priors, and constitutional rules.
        """
        # 1. Constitutional Veto (Lexicographic Safety Gate)
        applicable_rules = await self._get_applicable_rules(spec_constraints)
        for rule in applicable_rules:
            if rule.get("severity") in ["critical", "high"] and rule.get("deontic") == "MUST":
                return VerdictModel(
                    outcome="REJECT",
                    confidence=1.0,
                    uncertainty=0.0,
                    dissent=f"Rejected due to veto from high-severity constitutional rule: '{rule.get('name')}'.",
                    constitution_refs=[rule.get("id")],
                )

        # 2. Bayesian Aggregation
        confidence, uncertainty = self._bayesian_aggregation(
            participant_beliefs,
            calibration_priors,
        )

        # 3. Determine Outcome based on confidence threshold
        # This threshold could also be supplied by Synapse in the future.
        approval_threshold = 0.65
        if confidence > approval_threshold:
            outcome = "APPROVE"
        elif confidence < 0.35:
            outcome = "REJECT"
        else:
            outcome = "NEEDS_WORK"

        return VerdictModel(
            outcome=outcome,
            confidence=round(confidence, 4),
            uncertainty=round(uncertainty, 4),
            constitution_refs=[r.get("id") for r in applicable_rules],
        )
