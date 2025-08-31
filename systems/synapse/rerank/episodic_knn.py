# systems/synapse/rerank/episodic_knn.py
from __future__ import annotations

import numpy as np


class EpisodicKNN:
    """
    A k-Nearest Neighbors index over past episodes to suggest warm-start candidates.
    """

    _instance: EpisodicKNN | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, capacity: int = 5000):
        self._capacity = capacity
        self._contexts: np.ndarray | None = None
        self._arm_ids: list[str] = []
        self._rewards: list[float] = []
        self._next_idx = 0
        print(f"[EpisodicKNN] Warm-start index initialized with capacity {capacity}.")

    def update(self, x: np.ndarray, best_arm: str, reward: float):
        """
        Adds a new successful episode to the index.
        """
        # Only index episodes with positive rewards
        if reward < 0.5:
            return

        x = x.ravel()
        if self._contexts is None:
            self._contexts = np.zeros((self._capacity, x.shape[0]))

        # Use a circular buffer to store recent episodes
        self._contexts[self._next_idx] = x

        # Ensure arm_ids and rewards lists are the correct size
        if len(self._arm_ids) <= self._next_idx:
            self._arm_ids.extend([None] * (self._next_idx - len(self._arm_ids) + 1))
            self._rewards.extend([None] * (self._next_idx - len(self._rewards) + 1))

        self._arm_ids[self._next_idx] = best_arm
        self._rewards[self._next_idx] = reward

        self._next_idx = (self._next_idx + 1) % self._capacity

    def suggest(self, x: np.ndarray, k: int = 5) -> list[str]:
        """
        Suggests the top-k most promising arm_ids based on cosine similarity
        to the provided context vector.
        """
        if self._contexts is None or self._next_idx == 0:
            return []

        x = x.ravel()

        # Calculate cosine similarity
        # Use only the populated part of the buffer
        valid_contexts = self._contexts[: self._next_idx]
        dot_product = valid_contexts @ x
        norms = np.linalg.norm(valid_contexts, axis=1) * np.linalg.norm(x)
        similarities = dot_product / np.maximum(norms, 1e-9)  # Avoid division by zero

        # Get the indices of the top-k most similar contexts
        # We use `argpartition` for efficiency, as we don't need the full sort
        k = min(k, len(similarities))
        top_k_indices = np.argpartition(similarities, -k)[-k:]

        # Return the corresponding arm_ids, removing duplicates
        suggestions = list(
            set(self._arm_ids[i] for i in top_k_indices if self._arm_ids[i] is not None),
        )

        if suggestions:
            print(f"[EpisodicKNN] Suggested warm-start candidates: {suggestions}")
        return suggestions


# Singleton export
episodic_knn = EpisodicKNN()
