# systems/synapse/metacognitive_planner.py
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Optional

# Canonical, driverless access to the graph database.
from core.utils.neo.cypher_query import cypher_query

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger("Synapse.MetacognitivePlanner")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# -----------------------------------------------------------------------------
# Tunable weights (sane defaults)
# -----------------------------------------------------------------------------
W_GRAPH_FIT = 0.60  # risk/budget preference fit from the graph
W_RECENCY = 0.25  # fresher strategies/templates get a boost
W_EMPIRICAL_WIN = 0.15  # recent positive outcomes for this task

RECENCY_HALF_LIFE_DAYS = 14  # recency decay horizon

# The canonical fallback strategy. Ensures stability if the graph
# has no relevant strategy or an error occurs.
DEFAULT_STRATEGY: dict[str, Any] = {
    "mode": "DEFAULT_MODE",
    "objective_function": "balanced_performance",
    "constraints": [],
    "heuristics": [],
    "comment": "Default fallback strategy.",
}


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------
def _ctx_pick(
    primary: str | None,
    secondary: str | None,
    default: str | None,
) -> str | None:
    """Prefer primary, then secondary, then default."""
    return primary or secondary or default


def _safe_bool(v: Any) -> bool:
    return str(v).lower() in {"1", "true", "yes", "on"}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """
    Ultra-defensive getter that supports:
      - pydantic/BaseModel via getattr
      - simple objects / SimpleNamespace via getattr
      - dict-like via obj[key] / obj.get(key)
    """
    if obj is None:
        return default
    try:
        # Mapping first to avoid attribute shadowing
        if isinstance(obj, Mapping):
            return obj.get(key, default)
        # Pydantic/BaseModel/namespace-like
        if hasattr(obj, key):
            return getattr(obj, key, default)
    except Exception:
        pass
    return default


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
class MetacognitivePlanner:
    """
    Causal Strategic Planner for Synapse.

    Chooses a high-level strategy for a given task by consulting the Synk graph
    with contextual signals (risk/budget), while honoring explicit caller hints.
    Incorporates empirical feedback from recent outcomes for the same task_key.

    NOTE: This version intentionally avoids any *PolicyHint* types or imports.

    """

    _instance: MetacognitivePlanner | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def determine_strategy(self, request: Any) -> dict[str, Any]:
        """
        Determine the best strategy:
          1) If caller provides mode_hint, respect it immediately.
          2) Otherwise query the graph for candidate strategies tied to Task(key),
             scoring by: graph fit (risk/budget) + freshness + empirical wins.
          3) If no graph candidates, consult promoted dynamic templates (catalog).
          4) Else fall back to DEFAULT_STRATEGY.
        """
        task_key = _get(request, "task_key")
        if not task_key:
            logger.warning("[Metacog] No task_key provided; returning DEFAULT_STRATEGY.")
            return DEFAULT_STRATEGY

        logger.info("[Metacog] Determining strategy for task='%s'", task_key)

        # 1) Respect explicit guidance from caller when provided.
        mode_hint = _get(request, "mode_hint")
        if mode_hint:
            logger.info("[Metacog] Using caller-provided mode_hint='%s'", mode_hint)
            return {
                "mode": mode_hint,
                "objective_function": "guided_by_caller",
                "constraints": [],
                "heuristics": [],
                "comment": f"Mode provided by caller: {mode_hint}.",
            }

        # 2) Gather contextual signals (prefer rich context, fallback to legacy fields).
        ctx = _get(request, "context")

        risk_level = _ctx_pick(
            _get(ctx, "risk"),  # preferred in context
            _get(request, "risk"),  # legacy root field
            "medium",
        )
        budget_level = _ctx_pick(
            _get(ctx, "budget"),
            _get(request, "budget"),
            "normal",
        )

        prefer_exploitation = _safe_bool(_get(ctx, "prefer_exploitation", False))
        prefer_exploration = _safe_bool(_get(ctx, "prefer_exploration", False))

        logger.info(
            "[Metacog] Signals: risk=%s, budget=%s, exploit=%s, explore=%s",
            risk_level,
            budget_level,
            prefer_exploitation,
            prefer_exploration,
        )

        # 3) Query graph for Task-bound Strategy candidates and compute a composite score.
        strategy_rows: list[dict[str, Any]] = []
        try:
            strategy_rows = (
                await cypher_query(
                    """
                // Step A: retrieve graph-tied strategies for this Task
                OPTIONAL MATCH (t:Task {key:$task_key})-[:REQUIRES]->(s:Strategy)
                OPTIONAL MATCH (s)-[:PREFERS_RISK]->(r:Risk {level:$risk})
                OPTIONAL MATCH (s)-[:PREFERS_BUDGET]->(b:Budget {level:$budget})

                // Step B: empirical signals for this task (recent outcomes)
                // Count outcomes in the last RECENCY_HALF_LIFE_DAYS*2 window, weighting recent ones higher.
                WITH t, s, r, b,
                     coalesce(r.weight,0.0) + coalesce(b.weight,0.0) AS fit_score
                OPTIONAL MATCH (e:Episode {task_key:$task_key})-[:YIELDED]->(o:Outcome)
                WHERE o.ts >= datetime() - duration({days: $emp_window})
                WITH s, fit_score,
                     // recency of strategy
                     coalesce(s.updated_at, datetime({epochMillis:0})) AS s_updated,
                     // empirical: number of positive outcomes (reward > 0)
                     sum( CASE WHEN coalesce(o.reward,0.0) > 0.0 THEN 1 ELSE 0 END ) AS pos_outcomes

                // Compute normalized sub-scores
                WITH s, fit_score, s_updated, pos_outcomes,
                     duration.between(s_updated, datetime()).days AS days_old

                // recency_score in [0..1] via half-life style decay
                WITH s, fit_score, pos_outcomes,
                     CASE
                       WHEN $half_life <= 0 THEN 0.0
                       ELSE 1.0 / (1.0 + (toFloat(days_old) / toFloat($half_life)))
                     END AS recency_score

                // empirical_score in [0..1] via bounded mapping (capped)
                WITH s, fit_score, recency_score,
                     CASE
                       WHEN $emp_cap <= 0 THEN 0.0
                       ELSE toFloat(pos_outcomes) / toFloat($emp_cap)
                     END AS empirical_score

                RETURN
                  s.mode           AS mode,
                  s.objective      AS objective,
                  s.constraints    AS constraints,
                  s.heuristics     AS heuristics,
                  s.comment        AS comment,
                  fit_score        AS fit_score,
                  recency_score    AS recency_score,
                  empirical_score  AS empirical_score
                """,
                    {
                        "task_key": task_key,
                        "risk": risk_level,
                        "budget": budget_level,
                        "half_life": RECENCY_HALF_LIFE_DAYS,
                        # cap the denominator for empirical_score to avoid >1
                        "emp_cap": 20,  # treat 20 recent wins as "saturated"
                        "emp_window": 28,  # look back ~1 month
                    },
                )
                or []
            )
        except Exception as e:
            logger.warning(
                "[Metacog] Graph query for strategies failed: %s",
                e,
                exc_info=True,
            )
            strategy_rows = []

        def _row_score(r: dict[str, Any]) -> float:
            fit = float(r.get("fit_score", 0.0) or 0.0)
            rec = float(r.get("recency_score", 0.0) or 0.0)
            emp = float(r.get("empirical_score", 0.0) or 0.0)
            score = W_GRAPH_FIT * fit + W_RECENCY * rec + W_EMPIRICAL_WIN * emp
            if prefer_exploitation:
                # exploitation: upweight empirical wins and fit slightly
                score *= 1.10 + 0.10 * emp
            elif prefer_exploration:
                # exploration: downweight empirical, upweight recency
                score *= 0.95 + 0.20 * rec
            return score

        best: dict[str, Any] | None = None
        best_score = float("-inf")
        for row in strategy_rows:
            # skip empty rows (OPTIONAL MATCH may produce nulls)
            if not row or not (
                row.get("mode")
                or row.get("objective")
                or row.get("constraints")
                or row.get("heuristics")
            ):
                continue
            s = _row_score(row)
            if s > best_score:
                best, best_score = row, s

        if best:
            strategy = {
                "mode": best.get("mode") or "DEFAULT_MODE",
                "objective_function": best.get("objective") or "balanced_performance",
                "constraints": best.get("constraints") or [],
                "heuristics": best.get("heuristics") or [],
                "comment": best.get("comment")
                or (
                    "Graph strategy "
                    f"(score={round(best_score, 3)}, "
                    f"fit={round(best.get('fit_score', 0.0), 3)}, "
                    f"rec={round(best.get('recency_score', 0.0), 3)}, "
                    f"emp={round(best.get('empirical_score', 0.0), 3)})."
                ),
            }
            logger.info("[Metacog] Selected graph-defined strategy: %s", strategy["comment"])
            return strategy

        # 3b) No Task→Strategy rows? Try promoted dynamic templates (CatalogArm) to infer a mode.
        # This allows the system to generalize even when explicit strategies aren't modeled yet.
        try:
            tmpl_rows = (
                await cypher_query(
                    """
                // Pull top-performing catalog arms linked to any ArmTemplate
                // If you model task associations: (t:Task {key:$task_key})-[:GOOD_FOR]->(c:CatalogArm)
                // Here we fall back to global top arms if no task link exists.
                OPTIONAL MATCH (t:Task {key:$task_key})-[:GOOD_FOR]->(c:CatalogArm)
                WITH collect(c) AS cands
                CALL {
                  WITH cands
                  WITH CASE WHEN size(cands)>0 THEN cands ELSE null END AS cs
                  UNWIND (CASE WHEN cs IS NULL THEN [] ELSE cs END) AS c
                  RETURN c AS picked
                }
                WITH coalesce(picked, null) AS c
                OPTIONAL MATCH (c)<-[:PROMOTED_AS]-(t:ArmTemplate)
                WITH c, t
                RETURN
                  coalesce(c.mode, 'planful') AS mode,
                  coalesce(c.metrics.win_rate, 0.0) AS win_rate,
                  coalesce(c.metrics.recency, 0.0) AS recency,
                  t.plan_hash AS plan_hash
                ORDER BY win_rate DESC, recency DESC
                LIMIT 1
                """,
                    {"task_key": task_key},
                )
                or []
            )

            if tmpl_rows:
                tr = tmpl_rows[0]
                inferred_mode = tr.get("mode") or "generic"
                comment = f"Inferred from top CatalogArm (win_rate={round(float(tr.get('win_rate', 0.0)), 3)})."
                logger.info("[Metacog] Using catalog template inference: %s", comment)
                return {
                    "mode": inferred_mode,
                    "objective_function": "catalog_inferred",
                    "constraints": [],
                    "heuristics": [
                        {"hint": "seed_planner_with_template", "plan_hash": tr.get("plan_hash")},
                    ],
                    "comment": comment,
                }
        except Exception as e:
            logger.info("[Metacog] Catalog inference skipped (%s).", e, exc_info=True)

        # 4) Safe fallback.
        logger.info("[Metacog] Reverting to DEFAULT_STRATEGY.")
        return DEFAULT_STRATEGY


# Singleton export
metacognitive_planner = MetacognitivePlanner()
