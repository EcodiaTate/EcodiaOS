# systems/synapse/training/world_model_trainer.py
# NEW FILE (hardened)
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.model_selection import train_test_split

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.world.simulator import world_model  # singleton that exposes load_model()

logger = logging.getLogger(__name__)

# Model artifact location
MODEL_STORE_PATH = Path(os.getenv("SYNAPSE_MODEL_STORE", "/app/.synapse/models/"))
WORLD_MODEL_PATH = MODEL_STORE_PATH / "world_model_v1.joblib"


class WorldModelTrainer:
    """
    Handles offline training of the counterfactual world model.
    Trains a separate regressor for each reward dimension and persists a single artifact:
      {'vectorizer': DictVectorizer, 'models': [GBR, ...], 'metadata': {...}}
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        try:
            MODEL_STORE_PATH.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.exception(
                "[WorldModelTrainer] Failed to ensure model store directory: %s",
                MODEL_STORE_PATH,
            )

    # ---------------------
    # Featurization
    # ---------------------
    def _featurize_episode(self, episode: dict[str, Any]) -> dict[str, float] | None:
        """
        Convert a rich episode log into a flat feature dict.
        Uses x_context vector directly and normalizes dtypes.
        """
        try:
            ctx = episode["x_context"]
            if ctx is None:
                return None
            if isinstance(ctx, np.ndarray):
                ctx = ctx.tolist()
            if not isinstance(ctx, list | tuple):
                return None

            feats: dict[str, float] = {}
            for i, v in enumerate(ctx):
                try:
                    feats[f"ctx_{i}"] = float(v)
                except Exception:
                    # If a value is non-numeric, drop this feature
                    continue
            if not feats:
                return None
            return feats
        except Exception:
            return None

    # ---------------------
    # Data Fetch
    # ---------------------
    async def fetch_training_data(self, limit: int = 20000) -> list[dict[str, Any]]:
        """
        Fetch episode logs with embedded context and reward vectors.
        Expects:
          - e.x_context: numeric vector
          - e.reward_vec: numeric vector [p_success, delta_cost, p_safety_hit, sigma, ...]
        """
        logger.info("[WorldModelTrainer] Fetching episode logs (limit=%d)...", limit)
        query = """
        MATCH (e:Episode)
        WHERE e.x_context IS NOT NULL AND e.reward_vec IS NOT NULL
        RETURN e.x_context AS x_context, e.reward_vec AS reward_vec
        ORDER BY e.created_at DESC
        LIMIT $limit
        """
        rows = await cypher_query(query, {"limit": limit}) or []
        return rows if isinstance(rows, list) else []

    # ---------------------
    # Training
    # ---------------------
    def _build_dataset(
        self,
        episodes: list[dict[str, Any]],
    ) -> tuple[np.ndarray | None, np.ndarray | None, DictVectorizer | None]:
        """
        Build (X, Y, vectorizer) from raw episodes.
        """
        features = [self._featurize_episode(ep) for ep in episodes]
        valid_idx = [i for i, f in enumerate(features) if f is not None]
        if not valid_idx:
            return None, None, None

        X_dicts = [features[i] for i in valid_idx]
        # Make Y a dense 2D float array
        try:
            Y_full = np.asarray([episodes[i]["reward_vec"] for i in valid_idx], dtype=float)
        except Exception:
            return None, None, None
        if Y_full.ndim == 1:
            Y_full = Y_full.reshape(-1, 1)

        vec = DictVectorizer(sparse=False)
        X = vec.fit_transform(X_dicts)
        return X, Y_full, vec

    def _train_models(
        self,
        X_tr: np.ndarray,
        Y_tr: np.ndarray,
        random_state: int = 42,
    ) -> list[GradientBoostingRegressor]:
        """
        Train a separate GradientBoostingRegressor for each output dimension.
        """
        n_targets = Y_tr.shape[1]
        models: list[GradientBoostingRegressor] = []
        for i in range(n_targets):
            m = GradientBoostingRegressor(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=3,
                subsample=0.9,
                random_state=random_state + i,
            )
            m.fit(X_tr, Y_tr[:, i])
            models.append(m)
        return models

    def _evaluate(
        self,
        X_val: np.ndarray,
        Y_val: np.ndarray,
        models: list[GradientBoostingRegressor],
    ) -> dict[str, float]:
        """
        Compute simple validation metrics (R2 and MSE, aggregated and per-dimension).
        """
        preds = np.column_stack([m.predict(X_val) for m in models])
        mse = float(np.mean((preds - Y_val) ** 2))
        # R2 averaged over targets
        r2s = []
        for j in range(Y_val.shape[1]):
            yj = Y_val[:, j]
            pj = preds[:, j]
            ss_res = float(np.sum((yj - pj) ** 2))
            ss_tot = float(np.sum((yj - np.mean(yj)) ** 2))
            r2s.append(0.0 if ss_tot <= 1e-12 else 1.0 - ss_res / ss_tot)
        r2 = float(np.mean(r2s)) if r2s else 0.0

        metrics = {"val_mse": mse, "val_r2": r2}
        for j, r in enumerate(r2s):
            metrics[f"val_r2_{j}"] = float(r)
        return metrics

    def _atomic_save(self, payload: dict[str, Any], path: Path) -> None:
        """
        Atomically persist the model artifact.
        """
        tmp_path = path.with_suffix(".tmp")
        joblib.dump(payload, tmp_path)
        os.replace(tmp_path, path)

    # ---------------------
    # Publish to Graph
    # ---------------------
    async def _persist_model_card(
        self,
        dims_in: int,
        dims_out: int,
        metrics: dict[str, float],
    ) -> None:
        """
        Versioned upsert of world model metadata to Neo4j.
        """
        await cypher_query(
            """
            MATCH (m:SynapseWorldModel)
            WITH coalesce(max(m.version), 0) AS v
            CREATE (new:SynapseWorldModel {
                id: 'world_model',
                version: v + 1,
                created_at: datetime(),
                dims_in: $dims_in,
                dims_out: $dims_out,
                store_path: $store_path,
                metrics: $metrics
            })
            """,
            {
                "dims_in": int(dims_in),
                "dims_out": int(dims_out),
                "store_path": str(WORLD_MODEL_PATH),
                "metrics": {k: float(v) for k, v in metrics.items()},
            },
        )

    # ---------------------
    # Public API
    # ---------------------
    async def train_and_save_model(self) -> None:
        """
        Main training loop:
          - fetch data
          - build dataset
          - split
          - train per-dimension regressors
          - evaluate
          - atomically persist artifact
          - publish model card
          - hot-reload live world_model
        """
        if self._lock.locked():
            logger.info("[WorldModelTrainer] Training already in progress; skipping.")
            return

        async with self._lock:
            episodes = await self.fetch_training_data()
            n = len(episodes)
            if n < 200:
                logger.info("[WorldModelTrainer] Insufficient data (%d episodes). Skipping.", n)
                return

            X, Y, vec = self._build_dataset(episodes)
            if X is None or Y is None or vec is None:
                logger.info("[WorldModelTrainer] No valid samples after featurization. Skipping.")
                return

            X_tr, X_val, Y_tr, Y_val = train_test_split(
                X,
                Y,
                test_size=0.15,
                random_state=42,
                shuffle=True,
            )

            models = self._train_models(X_tr, Y_tr, random_state=42)
            metrics = self._evaluate(X_val, Y_val, models)

            payload = {"vectorizer": vec, "models": models, "metadata": {"metrics": metrics}}
            try:
                self._atomic_save(payload, WORLD_MODEL_PATH)
                logger.info(
                    "[WorldModelTrainer] Model artifact saved → %s | val_r2=%.3f val_mse=%.6f",
                    WORLD_MODEL_PATH,
                    metrics.get("val_r2", 0.0),
                    metrics.get("val_mse", 0.0),
                )
            except Exception:
                logger.exception("[WorldModelTrainer] Failed to save model artifact.")
                return

            try:
                await self._persist_model_card(
                    dims_in=X.shape[1],
                    dims_out=Y.shape[1],
                    metrics=metrics,
                )
            except Exception:
                logger.exception("[WorldModelTrainer] Failed to publish model card to graph.")

            try:
                world_model.load_model()
                logger.info("[WorldModelTrainer] World model hot-reloaded.")
            except Exception:
                logger.exception("[WorldModelTrainer] Live world_model reload failed.")


# Singleton export
world_model_trainer = WorldModelTrainer()
