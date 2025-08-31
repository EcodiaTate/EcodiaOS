# systems/synapse/values/learner.py
# FINAL PRODUCTION VERSION
from __future__ import annotations

import math
from typing import Any

import numpy as np

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.reward import reward_arbiter


class ValueLearner:
    """
    Learns scalarization weights from human preference data, aligning the
    system's reward function with desired outcomes (H9, H22).
    UPGRADE: Implements a Bradley-Terry model for robust preference learning.
    """

    _instance: ValueLearner | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _fetch_preferences(self, limit: int = 500) -> list[dict[str, Any]]:
        """Fetches recent PreferenceIngest data from the graph."""
        query = """
        MATCH (chosen:Episode)<-[:CHOSE]-(p:Preference)-[:REJECTED]->(rejected:Episode)
        WHERE chosen.reward_vec IS NOT NULL AND rejected.reward_vec IS NOT NULL
        RETURN chosen.reward_vec as winner_vec, rejected.reward_vec as loser_vec
        ORDER BY p.created_at DESC
        LIMIT $limit
        """
        return await cypher_query(query, {"limit": limit}) or []

    def _bradley_terry_update(
        self,
        weights: np.ndarray,
        preferences: list[dict[str, Any]],
        learning_rate=0.01,
        epochs=10,
    ) -> np.ndarray:
        """
        Updates weights using logistic regression, which is equivalent to
        training a Bradley-Terry model on the preference pairs.
        """
        for _ in range(epochs):
            for pref in preferences:
                winner_vec = np.array(pref["winner_vec"])
                loser_vec = np.array(pref["loser_vec"])

                # The model assumes P(winner > loser) = sigmoid(weights.T @ (winner_vec - loser_vec))
                diff_vec = winner_vec - loser_vec

                # Calculate predicted probability
                score = np.dot(weights, diff_vec)
                prob_winner = 1 / (1 + math.exp(-score))

                # Calculate the gradient. The label is 1 (since winner won).
                gradient = (1 - prob_winner) * diff_vec

                # Update weights
                weights += learning_rate * gradient
        return weights

    async def run_learning_cycle(self):
        """
        Fetches preferences and updates the live reward scalarization weights
        by fitting a Bradley-Terry model.
        """
        print("[ValueLearner] Starting preference learning cycle...")
        preferences = await self._fetch_preferences()
        if not preferences:
            print("[ValueLearner] No new preference data to learn from.")
            return

        # Get the current weights as a numpy array
        current_weights_dict = reward_arbiter._scalarization_weights.copy()
        weight_keys = ["success", "cost", "latency", "safety_hit"]
        initial_weights = np.array([current_weights_dict.get(k, 0.0) for k in weight_keys])

        # Train the model to get new weights
        new_weights_array = self._bradley_terry_update(initial_weights, preferences)

        # Convert back to dictionary
        updated_weights_dict = dict(zip(weight_keys, new_weights_array))

        # Clamp weights to reasonable bounds to prevent drift
        updated_weights_dict["success"] = max(0.5, min(2.0, updated_weights_dict["success"]))
        updated_weights_dict["cost"] = max(-2.0, min(-0.1, updated_weights_dict["cost"]))

        reward_arbiter.update_scalarization_weights(updated_weights_dict)
        print(f"[ValueLearner] Updated reward weights from preferences: {updated_weights_dict}")


# Singleton export
value_learner = ValueLearner()
