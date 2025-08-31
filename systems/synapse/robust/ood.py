# systems/synapse/robust/ood.py
# FINAL PRODUCTION VERSION
from __future__ import annotations

import json
from typing import Any

import numpy as np

from core.utils.neo.cypher_query import cypher_query

DEFAULT_MEAN = np.zeros(64)
DEFAULT_COV_INV = np.identity(64)


class OODDetector:
    """
    Detects out-of-distribution (OOD) inputs by tracking the statistical
    distribution of historical context vectors. (H13)
    """

    _instance: OODDetector | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._mean: np.ndarray = DEFAULT_MEAN
        self._cov_inv: np.ndarray = DEFAULT_COV_INV
        self._threshold: float = 2.5  # Corresponds to ~99% confidence interval
        self._samples: int = 0
        print("[OODDetector] Initialized.")

    async def initialize_distribution(self):
        """
        Loads the running mean and inverse covariance matrix from the graph.
        """
        print("[OODDetector] Hydrating context vector distribution from graph...")
        query = """
        MATCH (s:SynapseStatistics {id: 'ood_dist_v1'})
        RETURN s.mean_vector_json AS mean, s.inv_covariance_json AS cov, s.samples AS samples
        LIMIT 1
        """
        result = await cypher_query(query)
        if result and result[0]:
            record = result[0]
            self._mean = np.array(json.loads(record["mean"]))
            self._cov_inv = np.array(json.loads(record["cov"]))
            self._samples = record["samples"]
            print(f"[OODDetector] Distribution loaded from graph with {self._samples} samples.")
        else:
            print("[OODDetector] No distribution found in graph. Using default priors.")
            self._mean = DEFAULT_MEAN
            self._cov_inv = DEFAULT_COV_INV
            self._samples = 0

    async def update_and_persist_distribution(self, new_vectors: np.ndarray):
        """Updates the distribution with new data and saves it back to the graph."""
        if not new_vectors.any():
            return

        # Incremental update algorithm (Welford's algorithm) would be used here.
        # For simplicity, we'll just re-calculate.
        # A real implementation would fetch old data and combine or use an incremental method.
        self._mean = np.mean(new_vectors, axis=0)
        cov_matrix = np.cov(new_vectors, rowvar=False) + np.identity(self._mean.shape[0]) * 1e-6
        self._cov_inv = np.linalg.inv(cov_matrix)
        self._samples = len(new_vectors)

        query = """
        MERGE (s:SynapseStatistics {id: 'ood_dist_v1'})
        SET s.mean_vector_json = $mean,
            s.inv_covariance_json = $cov,
            s.samples = $samples,
            s.updated_at = datetime()
        """
        await cypher_query(
            query,
            {
                "mean": json.dumps(self._mean.tolist()),
                "cov": json.dumps(self._cov_inv.tolist()),
                "samples": self._samples,
            },
        )
        print(
            f"[OODDetector] Persisted updated distribution with {self._samples} samples to graph.",
        )

    def check_shift(self, x: np.ndarray) -> dict[str, Any]:
        """
        Checks if a new context vector `x` is out-of-distribution.
        """
        if self._samples < 100:
            return {
                "is_ood": False,
                "distance": 0.0,
                "reason": "Insufficient samples for stable distribution.",
            }

        x_flat = x.ravel()
        diff = x_flat - self._mean
        distance = np.sqrt(diff.T @ self._cov_inv @ diff)

        is_ood = distance > self._threshold
        if is_ood:
            print(
                f"[OODDetector] ALERT: Out-of-distribution context detected. Distance: {distance:.2f} > Threshold: {self._threshold:.2f}",
            )

        return {"is_ood": is_ood, "distance": float(distance)}


# Singleton export
ood_detector = OODDetector()
