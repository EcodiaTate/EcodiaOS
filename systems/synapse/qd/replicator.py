# systems/synapse/qd/replicator.py
# FINAL, COMPLETE VERSION
from __future__ import annotations

import numpy as np

from systems.synapse.qd.map_elites import Niche


class Replicator:
    """
    Manages exploration budget using replicator dynamics over QD niches.
    This ensures the system dynamically focuses its evolutionary pressure on
    the most promising areas of the solution space. (H15)
    """

    _instance: Replicator | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, learning_rate: float = 0.1):
        # niche -> fitness_score (e.g., rolling average ROI)
        self._niche_fitness: dict[Niche, float] = {}
        # niche -> proportion of exploration budget
        self._niche_share: dict[Niche, float] = {}
        self._eta = learning_rate
        print("[Replicator] Replicator dynamics module initialized.")

    def update_fitness(self, niche: Niche, fitness_score: float):
        """
        Updates the rolling fitness score for a given niche using an
        exponential moving average.
        """
        current_fitness = self._niche_fitness.get(niche, fitness_score)
        self._niche_fitness[niche] = (1 - self._eta) * current_fitness + self._eta * fitness_score

        # Initialize share if this is a new niche
        if niche not in self._niche_share:
            self._niche_share[niche] = 1.0
            self._normalize_shares()

    def _normalize_shares(self):
        """Ensures the total share distribution sums to 1."""
        total_share = sum(self._niche_share.values())
        if total_share > 0:
            for niche in self._niche_share:
                self._niche_share[niche] /= total_share

    def rebalance_shares(self):
        """
        Re-calculates the exploration share for all niches based on their
        relative fitness, using the replicator equation.
        """
        if not self._niche_fitness:
            return

        avg_fitness = np.mean(list(self._niche_fitness.values())) if self._niche_fitness else 0.0

        for niche, fitness in self._niche_fitness.items():
            # Replicator equation: share_new = share_old * (fitness / avg_fitness)
            # Using exponential form for stability: exp(eta * (fitness - avg_fitness))
            growth_factor = np.exp(self._eta * (fitness - avg_fitness))
            self._niche_share[niche] *= growth_factor

        self._normalize_shares()
        print(f"[Replicator] Rebalanced exploration shares across {len(self._niche_share)} niches.")

    def sample_niche(self) -> Niche | None:
        """
        Samples a niche to explore, biased by the current share proportions.
        """
        if not self._niche_share:
            return None

        niches = list(self._niche_share.keys())
        proportions = list(self._niche_share.values())

        # numpy's choice function handles the sampling according to the distribution p
        sampled_index = np.random.choice(len(niches), p=proportions)
        return niches[sampled_index]

    def get_genesis_allocation(self, total_budget: int) -> dict[Niche, int]:
        """
        Translates niche shares into a concrete number of arms to generate for each niche.
        """
        if not self._niche_share:
            return {}

        allocations = {}
        # Allocate budget proportional to share, ensuring at least one for the top niches
        for niche, share in self._niche_share.items():
            allocations[niche] = max(1, int(round(share * total_budget)))

        # Ensure the total allocation doesn't exceed the budget due to rounding
        while sum(allocations.values()) > total_budget:
            # Decrement from the largest allocation
            max_niche = max(allocations, key=allocations.get)
            if allocations[max_niche] > 1:
                allocations[max_niche] -= 1
            else:
                break  # Avoid dropping below 1

        print(f"[Replicator] Allocated genesis budget of {total_budget}: {allocations}")
        return allocations


# Singleton export
replicator = Replicator()
