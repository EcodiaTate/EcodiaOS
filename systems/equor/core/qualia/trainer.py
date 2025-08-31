# systems/equor/core/qualia/trainer.py
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from core.llm.bus import event_bus
from core.utils.neo.cypher_query import cypher_query
from systems.equor.core.qualia.manifold import qualia_manifold

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def _models_dir() -> Path:
    root = os.getenv("ECODIA_MODELS_DIR", "/var/lib/ecodia/models")
    p = Path(root).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _artifact_paths() -> tuple[Path, Path]:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = _models_dir()
    return base / f"qualia_autoencoder.{ts}.npz", base / "qualia_autoencoder.latest.npz"


def _std_from(model) -> np.ndarray:
    # Mirrors manifold’s protected logic (safe floor)
    if getattr(model, "count", 0) < 2:
        return np.ones_like(model.mean)
    var = model.M2 / max(1, int(model.count) - 1)
    return np.sqrt(np.maximum(var, 1e-8))


def _reconstruct(model, x: np.ndarray) -> np.ndarray:
    """
    Reconstruct x using current model statistics and weights:
      z = (x - mean) / std
      y = W @ z
      z_hat = W.T @ y
      x_hat = z_hat * std + mean
    """
    mean = model.mean
    std = _std_from(model)
    z = (x - mean) / std
    y = model.W @ z
    z_hat = model.W.T @ y
    return z_hat * std + mean


# ---------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------
class AutoencoderTrainer:
    """
    Trainer for the streaming PCA autoencoder (Sanger’s rule).
    Uses the model’s own update() for learning and computes true reconstruction MSE.
    """

    def __init__(self, model):
        self.model = model

    def _prime_stats(self, X: np.ndarray) -> None:
        """
        Initialize/refresh running statistics from the dataset before learning.
        This makes reconstruction loss meaningful on the first epochs.
        """
        if X.size == 0:
            return
        mean = X.mean(axis=0)
        var = X.var(axis=0, ddof=1) if X.shape[0] > 1 else np.ones(X.shape[1])
        self.model.mean = mean.astype(np.float64, copy=True)
        self.model.M2 = (np.maximum(var, 1e-8) * max(1, X.shape[0] - 1)).astype(
            np.float64,
            copy=True,
        )
        self.model.count = int(X.shape[0])

    def _epoch_loss(self, X: np.ndarray) -> float:
        sse = 0.0
        for i in range(X.shape[0]):
            x = X[i]
            x_hat = _reconstruct(self.model, x)
            diff = x_hat - x
            sse += float(np.dot(diff, diff))
        return sse / float(X.shape[0])

    def train(self, data: np.ndarray, epochs: int = 10, shuffle: bool = True) -> dict[str, Any]:
        """
        Full training loop:
          - prime stats
          - epochs of online updates via model.update()
          - report final reconstruction MSE
        """
        if data.ndim != 2 or data.shape[1] != getattr(self.model, "input_dim", 4):
            raise ValueError(
                f"Training data shape {data.shape} incompatible with model input_dim={self.model.input_dim}",
            )
        n = data.shape[0]
        if n < 16:
            return {"status": "skipped", "reason": "insufficient_data", "n": n}

        logger.info("[AETrainer] Training on %d samples for %d epochs.", n, epochs)
        self._prime_stats(data)

        order = np.arange(n)
        for ep in range(epochs):
            if shuffle:
                np.random.shuffle(order)
            for idx in order:
                self.model.update(data[idx])

        loss = self._epoch_loss(data)
        logger.info("[AETrainer] Final reconstruction MSE: %.6f", loss)
        return {"status": "ok", "n": n, "epochs": epochs, "loss_mse": loss}

    def save_weights(self, path: str | Path) -> None:
        self.model.save_weights(path)


# ---------------------------------------------------------------------
# Background Trainer Service
# ---------------------------------------------------------------------
class ManifoldTrainer:
    """
    Periodically retrains the Qualia Manifold’s encoder from historical metrics,
    persists an artifact, hot-swaps it into the live manifold, and emits an update event.
    """

    _instance: ManifoldTrainer | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = qualia_manifold.get_model()
            cls._instance.trainer = AutoencoderTrainer(cls._instance.model)
        return cls._instance

    async def _fetch_training_data(self) -> np.ndarray:
        """
        Query historical raw InternalStateMetrics and assemble the dataset
        in the exact normalization used by the manifold.
        """
        logger.info("[ManifoldTrainer] Fetching historical internal state metrics...")
        rows = await cypher_query(
            """
            MATCH (e:Episode)
            WHERE e.metrics IS NOT NULL
            RETURN
              e.metrics.cognitive_load  AS load,
              e.metrics.dissonance_score AS dissonance,
              e.metrics.integrity_score  AS integrity,
              e.metrics.curiosity_score  AS curiosity
            ORDER BY coalesce(e.created_at, datetime({epochMillis:0})) ASC
            """,
        )
        if not rows:
            return np.empty((0, getattr(self.model, "input_dim", 4)), dtype=np.float64)

        data = np.array(
            [
                [
                    float(r.get("load", 0.0)) / 1000.0,
                    float(r.get("dissonance", 0.0)) / 10.0,
                    float(r.get("integrity", 1.0)),
                    float(r.get("curiosity", 0.0)) / 5.0,
                ]
                for r in rows
            ],
            dtype=np.float64,
        )
        logger.info("[ManifoldTrainer] Fetched %d samples.", data.shape[0])
        return data

    async def run_training_cycle(
        self,
        *,
        min_samples: int = 16,
        epochs: int = 10,
    ) -> dict[str, Any]:
        """
        Execute one cycle: fetch → train → persist → deploy → notify.
        Returns training metadata for auditability.
        """
        X = await self._fetch_training_data()
        if X.shape[0] < min_samples:
            msg = f"insufficient_data (have {X.shape[0]}, need >= {min_samples})"
            logger.warning("[ManifoldTrainer] %s. Skipping cycle.", msg)
            return {"status": "skipped", "reason": msg, "n": int(X.shape[0])}

        result = self.trainer.train(X, epochs=epochs, shuffle=True)

        # Persist artifact and deploy
        artifact_path, latest_path = _artifact_paths()
        self.trainer.save_weights(artifact_path)
        # Copy to 'latest' (symlinks may be restricted on some platforms)
        try:
            if latest_path.exists():
                latest_path.unlink()
            latest_path.write_bytes(artifact_path.read_bytes())
        except Exception:
            logger.exception("Failed to update latest artifact; continuing.")

        # Hot-swap into live manifold
        qualia_manifold.load_model_weights(str(latest_path))

        # Notify
        await event_bus.publish(
            "equor.qualia.model.updated",
            {
                "artifact": str(artifact_path),
                "latest": str(latest_path),
                "metrics": result,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
        logger.info("[ManifoldTrainer] Model updated and event emitted.")
        out = {"status": "ok", "artifact": str(artifact_path), **result}
        return out


# Singleton export
manifold_trainer = ManifoldTrainer()
