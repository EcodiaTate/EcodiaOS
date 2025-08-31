from __future__ import annotations

from typing import Any

# Canonical, driverless access to the graph database.
from core.utils.neo.cypher_query import cypher_query
from systems.synapse.schemas import PolicyHintRequest

# The canonical fallback strategy. Ensures stability if the graph
# has no relevant strategy or an error occurs.
DEFAULT_STRATEGY = {
    "mode": "DEFAULT_MODE",
    "objective_function": "balanced_performance",
    "constraints": [],
    "heuristics": [],
    "comment": "Default fallback strategy.",
}


def _ctx_pick(
    primary: str | None,
    secondary: str | None,
    default: str | None,
) -> str | None:
    """Prefer primary, then secondary, then default."""
    return primary if primary else (secondary if secondary else default)


class MetacognitivePlanner:
    """
    Causal Strategic Planner for Synapse.

    Chooses a high-level strategy for a given task by consulting the Synk graph
    with contextual signals (risk/budget), while honoring explicit caller hints.
    """

    _instance: MetacognitivePlanner | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def determine_strategy(self, request: PolicyHintRequest) -> dict[str, Any]:
        """
        Determine the best strategy:
          1) If caller provides mode_hint, respect it immediately.
          2) Else consult the graph for a Strategy connected to Task(key),
             ranked by contextual fit (risk/budget) and recency.
          3) Else fall back to DEFAULT_STRATEGY.
        """
        print(f"[MetacognitivePlanner] Determining strategy for task: {request.task_key}")

        # 1) Respect explicit guidance from caller when provided.
        mode_hint = getattr(request, "mode_hint", None)
        if mode_hint:
            return {
                "mode": mode_hint,
                "objective_function": "guided_by_caller",
                "constraints": [],
                "heuristics": [],
                "comment": f"Mode provided by caller: {mode_hint}.",
            }

        # 2) Gather contextual signals (prefer rich context, fallback to legacy fields).
        risk_level = _ctx_pick(
            getattr(getattr(request, "context", None), "risk", None),
            getattr(request, "risk", None),
            "medium",
        )
        budget_level = _ctx_pick(
            getattr(getattr(request, "context", None), "budget", None),
            getattr(request, "budget", None),
            "normal",
        )

        # 3) Query the graph for a suitable Strategy.
        # This query tolerates sparse graphs: it will still return a row even if
        # Risk/Budget preference nodes are absent (score defaults to 0).
        query = """
        MATCH (t:Task {key: $task_key})-[:REQUIRES]->(s:Strategy)
        OPTIONAL MATCH (s)-[:PREFERS_RISK]->(r:Risk {level: $risk})
        OPTIONAL MATCH (s)-[:PREFERS_BUDGET]->(b:Budget {level: $budget})
        WITH s,
             coalesce(r.weight, 0.0) + coalesce(b.weight, 0.0) AS fit_score
        RETURN s.mode             AS mode,
               s.objective        AS objective,
               s.constraints      AS constraints,
               s.heuristics       AS heuristics,
               s.comment          AS comment,
               coalesce(s.updated_at, datetime({epochMillis:0})) AS updated_at,
               fit_score
        ORDER BY fit_score DESC, updated_at DESC
        LIMIT 1
        """

        try:
            rows = (
                await cypher_query(
                    query,
                    {
                        "task_key": request.task_key,
                        "risk": risk_level,
                        "budget": budget_level,
                    },
                )
                or []
            )
            if rows:
                row = rows[0]
                mode = row.get("mode") or "DEFAULT_MODE"
                strategy = {
                    "mode": mode,
                    "objective_function": row.get("objective") or "balanced_performance",
                    "constraints": row.get("constraints") or [],
                    "heuristics": row.get("heuristics") or [],
                    "comment": row.get("comment")
                    or f"Graph strategy (fit_score={row.get('fit_score', 0)}).",
                }
                print(f"[MetacognitivePlanner] Found graph-defined strategy: {strategy['comment']}")
                return strategy
        except Exception as e:
            print(f"[MetacognitivePlanner] ERROR: Graph query failed: {e}")

        # 4) Safe fallback.
        print("[MetacognitivePlanner] Reverting to default strategy.")
        return DEFAULT_STRATEGY


# Singleton export
metacognitive_planner = MetacognitivePlanner()
