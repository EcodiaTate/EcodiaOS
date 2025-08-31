# systems/synapse/skills/manager.py
# NEW FILE
from __future__ import annotations

import numpy as np

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.schemas import TaskContext
from systems.synapse.skills.schemas import Option


class SkillsManager:
    """
    Manages the loading and selection of learned hierarchical skills (Options).
    """

    _instance: SkillsManager | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._options: list[Option] = []
        return cls._instance

    async def initialize(self):
        """Loads all discovered Option nodes from the graph into memory."""
        print("[SkillsManager] Initializing and loading Options from graph...")
        query = "MATCH (o:Option) RETURN o"
        results = await cypher_query(query) or []
        self._options = [Option(**row["o"]) for row in results]
        print(f"[SkillsManager] Loaded {len(self._options)} hierarchical skills.")

    def select_best_option(
        self,
        context_vec: np.ndarray,
        task_ctx: TaskContext,
    ) -> Option | None:
        """
        Checks if the current context is a suitable starting point for any known Option.
        """
        if not self._options:
            return None

        best_match: Option | None = None
        min_distance = float("inf")

        for option in self._options:
            # Simple check: cosine similarity to the option's initiation context
            # A real implementation could use a more sophisticated classifier.
            init_vec = np.array(option.initiation_set[0]["context_vec_mean"])

            # Cosine distance = 1 - cosine similarity
            similarity = (context_vec.T @ init_vec) / (
                np.linalg.norm(context_vec) * np.linalg.norm(init_vec)
            )
            distance = 1 - similarity

            if distance < 0.1 and distance < min_distance:  # Threshold for a good match
                min_distance = distance
                best_match = option

        if best_match:
            print(
                f"[SkillsManager] Found matching skill: Option {best_match.id} (distance: {min_distance:.4f})",
            )

        return best_match


# Singleton export
skills_manager = SkillsManager()
