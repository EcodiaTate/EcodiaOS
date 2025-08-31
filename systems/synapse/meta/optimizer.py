# systems/synapse/meta/optimizer.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, StandardScaler

from core.llm.bus import event_bus
from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)

# Search grids aligned to MetaController expectations
COGNITIVE_MODES: tuple[str, ...] = ("greedy", "reflective", "planful", "consensus")
CRITIC_BLEND_GRID: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40, 0.55, 0.60, 0.70)
REFLECTION_DEPTH_GRID: tuple[int, ...] = (0, 1, 2, 3)

MIN_SAMPLES_PER_RISK = 30  # avoid overfitting; skip risk bucket if too small


@dataclass
class _EpisodeRow:
    risk: str
    cognitive_mode: str | None
    critic_blend: float | None
    reflection_depth: int | None
    target: float


class MetaOptimizer:
    """
    Optimizes Synapse hyperparameters by replay-style modeling over historical episodes.
    Produces strategy_map compatible with MetaController:
      { "low": {"cognitive_mode": "...", "critic_blend": 0.3, "reflection_depth": 1}, ... }
    """

    _instance: MetaOptimizer | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _fetch_replay_data(self, limit: int = 5000) -> list[_EpisodeRow]:
        """
        Pull historical episodes with reward and policy metadata.
        Tolerates schema drift by coalescing common property names.
        """
        rows = (
            await cypher_query(
                """
            MATCH (e:Episode)
            WHERE coalesce(e.roi, e.reward, e.return, e.score) IS NOT NULL
            WITH e
            OPTIONAL MATCH (e)-[:USED_POLICY]->(p:Policy)
            RETURN
              toString(coalesce(e.risk_level, p.risk_level, 'medium')) AS risk,
              toString(coalesce(e.cognitive_mode, p.cognitive_mode))    AS cognitive_mode,
              toFloat(coalesce(e.critic_blend, e.critic_blend_factor, p.critic_blend, 0.3)) AS critic_blend,
              toInteger(coalesce(e.reflection_depth, p.reflection_depth, 1)) AS reflection_depth,
              toFloat(coalesce(e.roi, e.reward, e.return, e.score))     AS target
            ORDER BY coalesce(e.ended_at, e.created_at, datetime({epochMillis:0})) DESC
            LIMIT $limit
            """,
                {"limit": limit},
            )
            or []
        )

        data: list[_EpisodeRow] = []
        for r in rows:
            risk = (r.get("risk") or "medium").lower()
            cmode = (r.get("cognitive_mode") or "").lower() or None
            # Guard ranges
            cb = float(r.get("critic_blend", 0.3))
            cb = float(min(max(cb, 0.0), 1.0))
            rd = int(max(0, int(r.get("reflection_depth", 1))))
            tgt = float(r.get("target", 0.0))
            data.append(
                _EpisodeRow(
                    risk=risk,
                    cognitive_mode=cmode,
                    critic_blend=cb,
                    reflection_depth=rd,
                    target=tgt,
                ),
            )
        return data

    def _fit_model(self, rows: list[_EpisodeRow]) -> Pipeline | None:
        """
        Fit a predictive model target ~ f(cognitive_mode, critic_blend, reflection_depth, interactions).
        Returns a scikit-learn Pipeline or None if insufficient data.
        """
        if len(rows) < MIN_SAMPLES_PER_RISK:
            return None

        X_cmode = np.array([r.cognitive_mode or "reflective" for r in rows], dtype=object).reshape(
            -1,
            1,
        )
        X_num = np.array(
            [[r.critic_blend or 0.3, r.reflection_depth or 1] for r in rows],
            dtype=float,
        )
        y = np.array([r.target for r in rows], dtype=float)

        # ColumnTransformer: one-hot cognitive_mode + scaled numerics + quadratic interactions on numerics
        ColumnTransformer(
            transformers=[
                (
                    "cmode",
                    OneHotEncoder(handle_unknown="ignore", categories=[list(COGNITIVE_MODES)]),
                    [0],
                ),
                (
                    "num",
                    Pipeline(
                        [
                            ("scale", StandardScaler()),
                            ("poly", PolynomialFeatures(degree=2, include_bias=False)),
                        ],
                    ),
                    [1, 2],
                ),
            ],
            remainder="drop",
        )

        model = Pipeline(
            steps=[
                (
                    "merge",
                    ColumnTransformer(
                        [
                            (
                                "cmode",
                                OneHotEncoder(
                                    handle_unknown="ignore",
                                    categories=[list(COGNITIVE_MODES)],
                                ),
                                [0],
                            ),
                            ("num", StandardScaler(), [1, 2]),
                        ],
                        remainder="drop",
                    ),
                ),
                ("poly", PolynomialFeatures(degree=2, include_bias=False)),
                ("ridge", RidgeCV(alphas=np.logspace(-3, 3, 13), store_cv_values=False)),
            ],
        )

        # Fit on concatenated input (cmode, critic_blend, reflection_depth)
        X = np.concatenate([X_cmode, X_num], axis=1)
        model.fit(X, y)
        return model

    def _predict_reward(self, model: Pipeline, cmode: str, cb: float, rd: int) -> float:
        X = np.array([[cmode, float(cb), int(rd)]], dtype=object)
        return float(model.predict(X)[0])

    def _search_best(self, model: Pipeline) -> dict[str, Any]:
        """
        Grid-search the discrete space for the best policy triple.
        """
        best = {
            "cognitive_mode": "reflective",
            "critic_blend": 0.30,
            "reflection_depth": 1,
            "score": -1e18,
        }
        for cm in COGNITIVE_MODES:
            for cb in CRITIC_BLEND_GRID:
                for rd in REFLECTION_DEPTH_GRID:
                    s = self._predict_reward(model, cm, cb, rd)
                    if s > best["score"]:
                        best = {
                            "cognitive_mode": cm,
                            "critic_blend": float(cb),
                            "reflection_depth": int(rd),
                            "score": float(s),
                        }
        return best

    async def run_optimization_cycle(self) -> dict[str, Any]:
        """
        End-to-end optimization:
          - Pull history
          - Train per-risk models
          - Choose best triple per risk
          - Persist :SynapseHyperparameters version with strategy_map
          - Emit optimization event
        """
        logger.info("[MetaOptimizer] Starting optimization cycle.")
        rows = await self._fetch_replay_data()
        if not rows:
            msg = "no_historical_data"
            logger.warning("[MetaOptimizer] %s", msg)
            return {"status": "skipped", "reason": msg}

        by_risk: dict[str, list[_EpisodeRow]] = {"low": [], "medium": [], "high": []}
        for r in rows:
            key = r.risk if r.risk in by_risk else "medium"
            by_risk[key].append(r)

        strategy_map: dict[str, dict[str, Any]] = {}
        models_info: dict[str, dict[str, Any]] = {}
        any_trained = False

        for risk in ("low", "medium", "high"):
            bucket = by_risk[risk]
            model = self._fit_model(bucket)
            if model is None:
                logger.warning(
                    "[MetaOptimizer] Insufficient samples for risk='%s' (n=%d). Skipping.",
                    risk,
                    len(bucket),
                )
                continue
            any_trained = True
            best = self._search_best(model)
            strategy_map[risk] = {
                "cognitive_mode": best["cognitive_mode"],
                "critic_blend": best["critic_blend"],
                "reflection_depth": best["reflection_depth"],
            }
            # Baseline vs predicted best diagnostics
            baseline = float(np.mean([b.target for b in bucket])) if bucket else 0.0
            models_info[risk] = {
                "n": len(bucket),
                "predicted_best_reward": best["score"],
                "baseline_mean_reward": baseline,
                "uplift": best["score"] - baseline,
            }
            logger.info(
                "[MetaOptimizer] risk=%s best=%s predicted=%.4f baseline=%.4f",
                risk,
                strategy_map[risk],
                best["score"],
                baseline,
            )

        if not any_trained:
            logger.warning(
                "[MetaOptimizer] No buckets met the minimum sample requirement; aborting.",
            )
            return {"status": "skipped", "reason": "insufficient_samples_all_buckets"}

        # Persist new version
        payload = {
            "strategy_map": json.dumps(strategy_map, separators=(",", ":"), ensure_ascii=False),
            "score": float(np.mean([v["uplift"] for v in models_info.values()])),
            "meta": json.dumps(models_info, separators=(",", ":"), ensure_ascii=False),
        }

        await cypher_query(
            """
            MATCH (c:SynapseHyperparameters)
            WITH coalesce(max(c.version), 0) AS latest
            CREATE (new:SynapseHyperparameters {
              version: latest + 1,
              created_at: datetime(),
              strategy_map: $strategy_map,
              score: $score,
              meta: $meta,
              method: 'ridgecv_grid'
            })
            """,
            payload,
        )

        await event_bus.publish(
            "synapse.meta.optimized",
            {"strategy_map": strategy_map, "models": models_info},
        )
        logger.info("[MetaOptimizer] Optimization complete and persisted.")

        return {"status": "ok", "strategy_map": strategy_map, "diagnostics": models_info}


# Singleton export
meta_optimizer = MetaOptimizer()
