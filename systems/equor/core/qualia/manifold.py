from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from core.llm.bus import event_bus
from systems.equor.core.neo import graph_writes
from systems.equor.schemas import InternalStateMetrics, QualiaState

logger = logging.getLogger(__name__)


# ------------------------------
# Online PCA Autoencoder (k PCs)
# ------------------------------
@dataclass
class _AEWeights:
    input_dim: int
    latent_dim: int
    count: int
    mean: np.ndarray
    M2: np.ndarray
    W: np.ndarray  # shape: (latent_dim, input_dim)

    def to_npz(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            input_dim=self.input_dim,
            latent_dim=self.latent_dim,
            count=self.count,
            mean=self.mean,
            M2=self.M2,
            W=self.W,
            version=np.array([1], dtype=np.int32),
        )

    @staticmethod
    def from_npz(path: str | Path) -> _AEWeights:
        d = np.load(Path(path))
        return _AEWeights(
            int(d["input_dim"]),
            int(d["latent_dim"]),
            int(d["count"]),
            d["mean"].astype(np.float64),
            d["M2"].astype(np.float64),
            d["W"].astype(np.float64),
        )


class TrainedAutoencoder:
    """
    Streaming linear autoencoder via Sanger's rule (generalized Hebbian learning):
      - Maintains running mean/variance (Welford) for standardization
      - Learns top-k principal components online
      - Provides encode(x) = W @ z, where z = standardize(x)

    This requires no external ML deps and is fully deterministic after init.
    """

    def __init__(self, input_dim: int = 4, latent_dim: int = 2, eta0: float = 0.15):
        if latent_dim < 1 or latent_dim > input_dim:
            raise ValueError("latent_dim must be in [1, input_dim].")
        self.input_dim = int(input_dim)
        self.latent_dim = int(latent_dim)
        self.eta0 = float(eta0)

        # Running statistics for standardization
        self.count = 0
        self.mean = np.zeros(self.input_dim, dtype=np.float64)
        self.M2 = np.zeros(self.input_dim, dtype=np.float64)  # sum of squared diffs

        # Deterministic orthonormal initialization: first k basis vectors
        self.W = np.zeros((self.latent_dim, self.input_dim), dtype=np.float64)
        for i in range(self.latent_dim):
            self.W[i, i] = 1.0

        logger.info(
            "[QualiaAE] Initialized: input_dim=%d latent_dim=%d",
            self.input_dim,
            self.latent_dim,
        )

    # --------- Persistence ---------
    def save_weights(self, path: str | Path) -> None:
        _AEWeights(self.input_dim, self.latent_dim, self.count, self.mean, self.M2, self.W).to_npz(
            path,
        )
        logger.info("[QualiaAE] Weights saved to %s", path)

    def load_weights(self, path: str | Path) -> None:
        w = _AEWeights.from_npz(path)
        if w.input_dim != self.input_dim or w.latent_dim != self.latent_dim:
            raise ValueError(
                f"Weight shape mismatch: model ({self.input_dim},{self.latent_dim}) vs file ({w.input_dim},{w.latent_dim})",
            )
        self.count, self.mean, self.M2, self.W = w.count, w.mean, w.M2, w.W
        logger.info("[QualiaAE] Weights loaded from %s (count=%d)", path, self.count)

    # --------- Core math ---------
    def _std(self) -> np.ndarray:
        # Robust per-feature std; avoid zero by floor at 1e-8
        if self.count < 2:
            return np.ones_like(self.mean)
        var = self.M2 / max(1, self.count - 1)
        return np.sqrt(np.maximum(var, 1e-8))

    def _standardize(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self._std()

    def _update_stats(self, x: np.ndarray) -> None:
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        delta2 = x - self.mean
        self.M2 += delta * delta2

    def _eta(self) -> float:
        # Diminishing learning rate; bounded away from zero
        return max(self.eta0 / np.sqrt(max(1.0, float(self.count))), 1e-3)

    def encode(self, metrics_vector: np.ndarray) -> np.ndarray:
        """
        Encode a single vector with current weights (no parameter updates).
        """
        x = np.asarray(metrics_vector, dtype=np.float64).reshape(-1)
        if x.shape[0] != self.input_dim:
            raise ValueError(f"Input dim {x.shape[0]} != expected {self.input_dim}")
        z = self._standardize(x)
        return self.W @ z

    def update(self, metrics_vector: np.ndarray) -> None:
        """
        Online learning step using Sanger's rule.
        """
        x = np.asarray(metrics_vector, dtype=np.float64).reshape(-1)
        if x.shape[0] != self.input_dim:
            raise ValueError(f"Input dim {x.shape[0]} != expected {self.input_dim}")

        # Update running stats first; learn in standardized space
        self._update_stats(x)
        z = self._standardize(x)

        y = self.W @ z  # projections (k,)
        eta = self._eta()

        proj_prefix = np.zeros(self.input_dim, dtype=np.float64)
        for i in range(self.latent_dim):
            wi = self.W[i]
            yi = float(y[i])
            if i == 0:
                proj_prefix = yi * wi
            else:
                proj_prefix = proj_prefix + yi * wi
            correction = z - proj_prefix
            wi = wi + eta * yi * correction
            norm = np.linalg.norm(wi)
            if norm > 1e-12:
                wi /= norm
            self.W[i] = wi


# ------------------------------
# Manifold + Logging
# ------------------------------
class QualiaManifold:
    _instance: QualiaManifold | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_model()
        return cls._instance

    def _init_model(self) -> None:
        # 4 input dims correspond to (cognitive_load, dissonance, integrity, curiosity)
        self.autoencoder = TrainedAutoencoder(input_dim=4, latent_dim=2)

    def get_model(self) -> TrainedAutoencoder:
        """Expose the trainable model for external trainers/tools."""
        return self.autoencoder

    def load_model_weights(self, path: str) -> None:
        """Load persisted weights (npz) and hot-swap into the live model."""
        self.autoencoder.load_weights(path)

    def process_metrics(self, metrics: InternalStateMetrics) -> QualiaState:
        """
        Transform InternalStateMetrics -> QualiaState via current encoder,
        then update the model online with the new observation.
        """
        v = np.array(
            [
                float(metrics.cognitive_load) / 1000.0,
                float(metrics.dissonance_score) / 10.0,
                float(metrics.integrity_score),
                float(metrics.curiosity_score) / 5.0,
            ],
            dtype=np.float64,
        )

        coords = self.autoencoder.encode(v)
        self.autoencoder.update(v)

        return QualiaState(
            id=f"qs_{uuid.uuid4().hex}",
            timestamp=datetime.now(UTC).isoformat(),
            manifold_coordinates=coords.tolist(),
            triggering_episode_id=metrics.episode_id,
        )


class StateLogger:
    _instance: StateLogger | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.manifold = QualiaManifold()
        return cls._instance

    async def log_state(self, metrics: InternalStateMetrics) -> None:
        """
        Persist a QualiaState and publish an event, with raw metrics attached to the Episode.
        """
        logger.info("[StateLogger] Logging internal state for episode '%s'.", metrics.episode_id)

        qualia_state = self.manifold.process_metrics(metrics)
        await graph_writes.save_qualia_state(qualia_state)
        await graph_writes.attach_metrics_to_episode(metrics)

        # FIX: Publish the qualia_state object directly without the extra wrapper key.
        # The subscriber expects a dictionary that maps directly to the QualiaState model.
        await event_bus.publish(
            "equor.qualia.state.created",
            qualia_state.model_dump(),
        )
        logger.info("[StateLogger] Emitted qualia state '%s'.", qualia_state.id)


# Singleton exports
state_logger = StateLogger()
qualia_manifold = QualiaManifold()
