# systems/synapse/training/meta_controller.py
from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.tactics import TacticalManager
from systems.synk.core.switchboard.gatekit import gated_loop

# Default configuration for the meta-controller. These values are used only if
# no configuration is found in the knowledge graph, ensuring system stability.
DEFAULT_CONFIG: dict[str, Any] = {
    "recent_episode_window": 50,  # number of most-recent episodes per mode to average
    "performance_threshold": 0.05,
    "adjustment_factor": 1.2,
    "min_alpha": 0.25,
    "max_alpha": 3.0,
}


class MetaController:
    """
    The "learning-to-learn" engine for Synapse.

    It queries the Synk graph for performance trends of all tactical bandits and
    dynamically tunes their hyperparameters (`alpha`) to optimize exploration vs exploitation.
    """

    _instance: MetaController | None = None
    _config: dict[str, Any] = DEFAULT_CONFIG.copy()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """
        Loads the meta-controller's operational parameters from the graph.
        """
        print("[MetaController] Initializing configuration from graph...")
        # Return the whole node as 'config' so field access is straightforward.
        query = "MATCH (c:MetaControllerConfig) RETURN c AS config LIMIT 1"
        try:
            rows = await cypher_query(query) or []
            if rows and isinstance(rows[0], dict) and rows[0].get("config"):
                node_props: dict[str, Any] = rows[0]["config"]
                # Merge graph props over defaults (only keys we know)
                merged = DEFAULT_CONFIG.copy()
                for k, v in DEFAULT_CONFIG.items():
                    if k in node_props and node_props[k] is not None:
                        merged[k] = node_props[k]
                self._config = merged
                print("[MetaController] Configuration loaded from graph.")
            else:
                print("[MetaController] No config found in graph. Using default values.")
                self._config = DEFAULT_CONFIG.copy()
        except Exception as e:
            print(f"[MetaController] ERROR loading config, using defaults: {e}")
            self._config = DEFAULT_CONFIG.copy()

        # Final safety: cast window to int, clamp to sane range
        try:
            w = int(self._config.get("recent_episode_window", 50))
            self._config["recent_episode_window"] = max(1, min(w, 1000))
        except Exception:
            self._config["recent_episode_window"] = 50

    async def run_tuning_cycle(self):
        """
        Executes one cycle of performance analysis and hyperparameter tuning.
        """
        print("[MetaController] Starting tuning cycle...")

        # IMPORTANT:
        # - Sort by created_at descending, collect rewards per mode,
        # - Slice to top-$window for "recent", UNWIND both lists for avg of scalars.
        query = """
        MATCH (e:Episode)
        WHERE e.mode IS NOT NULL AND e.reward IS NOT NULL
        WITH e.mode AS mode, e
        ORDER BY coalesce(e.created_at, datetime({epochMillis:0})) DESC
        WITH mode, collect(toFloat(e.reward)) AS rewards, $window AS window
        WITH mode, rewards, rewards[..window] AS recent_list
        UNWIND rewards AS all_r
        WITH mode, recent_list, avg(all_r) AS long_term_reward
        UNWIND recent_list AS r
        WITH mode, long_term_reward, avg(r) AS recent_reward
        RETURN mode, long_term_reward, recent_reward
        """

        try:
            params = {"window": int(self._config.get("recent_episode_window", 50))}
            results = await cypher_query(query, params) or []
        except Exception as e:
            print(f"[MetaController] ERROR fetching performance data: {e}")
            return

        for record in results:
            mode = record.get("mode")
            long_term_reward = record.get("long_term_reward")
            recent_reward = record.get("recent_reward")

            if not mode or recent_reward is None:
                continue

            bandit = TacticalManager.get(mode)
            if not bandit:
                print(f"[MetaController] WARNING: Unknown mode '{mode}'. Skipping.")
                continue

            current_alpha = getattr(bandit, "alpha", 1.0)
            new_alpha = current_alpha
            threshold = float(self._config.get("performance_threshold", 0.05))
            factor = float(self._config.get("adjustment_factor", 1.2))
            min_alpha = float(self._config.get("min_alpha", 0.25))
            max_alpha = float(self._config.get("max_alpha", 3.0))

            base = float(long_term_reward or 0.0)
            rr = float(recent_reward)

            # Adaptive alpha policy based on performance trends.
            if rr < base - threshold:
                # Performance dropped; increase alpha to explore more.
                new_alpha = min(current_alpha * factor, max_alpha)
                print(
                    f"[MetaController] Mode '{mode}' performance dropped ({rr:.3f} vs {base:.3f}). Increasing alpha -> {new_alpha:.2f}",
                )
            elif rr > base + threshold:
                # Performance strong; decrease alpha to exploit more.
                new_alpha = max(current_alpha / factor, min_alpha)
                print(
                    f"[MetaController] Mode '{mode}' performance strong ({rr:.3f} vs {base:.3f}). Decreasing alpha -> {new_alpha:.2f}",
                )

            bandit.alpha = new_alpha


async def start_meta_controller_loop():
    """
    Daemon function to run the meta-controller periodically.
    """
    controller = MetaController()
    await controller.initialize()  # Load config before starting the loop.

    await gated_loop(
        task_coro=controller.run_tuning_cycle,
        enabled_key="synapse.train.enabled",
        interval_key="synapse.meta_controller.interval_sec",
        default_interval=900,  # Run every 15 minutes by default
    )
