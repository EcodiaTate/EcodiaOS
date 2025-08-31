# systems/synapse/training/neural_linear.py
from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Helpers for serializing numpy arrays for Neo4j
# ---------------------------------------------------------------------
def _pack_matrix(M: np.ndarray) -> tuple[list, tuple[int, int]]:
    """Return (flat_list, shape) for storage in Neo4j."""
    if not isinstance(M, np.ndarray):
        M = np.asarray(M, dtype=float)
    if M.ndim == 1:
        M = M.reshape(-1, 1)
    shape = (int(M.shape[0]), int(M.shape[1]))
    flat = M.reshape(-1).astype(float).tolist()
    return flat, shape


def _unpack_matrix(flat: list, shape: tuple[int, int]) -> np.ndarray:
    """Rebuild numpy matrix from (flat_list, shape)."""
    if not flat or not shape or len(shape) != 2:
        raise ValueError("Invalid matrix persistence payload")
    r, c = int(shape[0]), int(shape[1])
    arr = np.asarray(flat, dtype=float).reshape((r, c))
    return arr


def _ensure_col_vec(x: np.ndarray) -> np.ndarray:
    """Ensure x is a (d,1) column vector of dtype float64."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    elif x.ndim == 2 and x.shape[1] != 1 and x.shape[0] == 1:
        x = x.T
    if x.ndim != 2 or x.shape[1] != 1:
        raise ValueError(f"Context vector must be (d,1) column; got shape {x.shape}")
    return x


def _stable_cholesky(A: np.ndarray, max_tries: int = 5) -> np.ndarray:
    """
    Cholesky with diagonal jitter to guarantee PD factorization for sampling/solves.
    Returns lower-triangular L such that (A + eps*I) = L L^T.
    """
    I = np.eye(A.shape[0], dtype=np.float64)
    eps = 1e-10
    for k in range(max_tries):
        try:
            return np.linalg.cholesky(A + eps * I)
        except np.linalg.LinAlgError:
            eps *= 10.0
    # Last attempt; if it still fails, raise
    return np.linalg.cholesky(A + eps * I)


# ---------------------------------------------------------------------
# Neural Linear Head (Bayesian linear regression with forgetting)
# ---------------------------------------------------------------------
class NeuralLinearBanditHead:
    """
    Bayesian Linear Regression head for a single arm.
    Uses Thompson Sampling:
      Posterior precision A = λI + Σ γ^t x xᵀ
      Posterior mean θ̂ solves A θ̂ = b, with b = Σ γ^t r x
    """

    __slots__ = ("id", "A", "b", "_d", "lambda_prior", "_gamma")

    def __init__(
        self,
        arm_id: str,
        dimensions: int,
        lambda_prior: float = 1.0,
        initial_state: dict[str, Any] | None = None,
        gamma: float = 0.995,
    ):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if lambda_prior <= 0:
            raise ValueError("lambda_prior must be > 0")
        if not (0.0 < gamma <= 1.0):
            raise ValueError("gamma must be in (0,1]")

        self.id = arm_id
        self._d = int(dimensions)
        self.lambda_prior = float(lambda_prior)
        self._gamma = float(gamma)

        if initial_state:
            self.A = _unpack_matrix(initial_state["A"], tuple(initial_state["A_shape"]))
            self.b = _unpack_matrix(initial_state["b"], tuple(initial_state["b_shape"]))
            # Validate shapes
            if self.A.shape != (self._d, self._d):
                raise ValueError(
                    f"Loaded A has shape {self.A.shape}, expected ({self._d},{self._d})",
                )
            if self.b.shape != (self._d, 1):
                raise ValueError(f"Loaded b has shape {self.b.shape}, expected ({self._d},1)")
        else:
            self.A = np.eye(self._d, dtype=np.float64) * self.lambda_prior
            self.b = np.zeros((self._d, 1), dtype=np.float64)

    # ---------- Persistence ----------
    def get_state(self) -> dict[str, Any]:
        """Returns the serializable state of the bandit head."""
        A_flat, A_shape = _pack_matrix(self.A)
        b_flat, b_shape = _pack_matrix(self.b)
        return {"A": A_flat, "A_shape": list(A_shape), "b": b_flat, "b_shape": list(b_shape)}

    # ---------- Posterior ----------
    def _posterior_mean(self) -> np.ndarray:
        """
        Solve A θ = b via Cholesky for numerical stability.
        Returns θ as (d,1).
        """
        L = _stable_cholesky(self.A)
        # Solve L y = b
        y = np.linalg.solve(L, self.b)
        # Solve L^T θ = y
        theta = np.linalg.solve(L.T, y)
        return theta

    def sample_theta(self) -> np.ndarray:
        """
        Draw a single θ sample ~ N(μ, A^{-1}) using Cholesky solves:
          Let A = L L^T. For z ~ N(0, I), u = solve(L, z), w = solve(L^T, u),
          θ = μ + w
        Returns (d,1).
        """
        L = _stable_cholesky(self.A)
        mu = self._posterior_mean()
        z = np.random.normal(size=(self._d, 1))
        u = np.linalg.solve(L, z)
        w = np.linalg.solve(L.T, u)
        return mu + w

    def get_theta_mean(self) -> np.ndarray:
        """Returns the posterior mean θ̂ = A^{-1} b as (d,1)."""
        return self._posterior_mean()

    def score(self, x: np.ndarray) -> float:
        """
        Thompson-sampled score for context x (column vector).
        """
        x = _ensure_col_vec(x)
        theta = self.sample_theta()
        return float((theta.T @ x).ravel()[0])

    def update(self, x: np.ndarray, r: float, gamma: float | None = None) -> None:
        """
        Update with context x and scalar reward r.
        Uses exponential forgetting on sufficient statistics:
          A ← γ A + x xᵀ
          b ← γ b + r x
        """
        x = _ensure_col_vec(x)
        g = float(self._gamma if gamma is None else gamma)
        if not (0.0 < g <= 1.0):
            raise ValueError("gamma must be in (0,1]")

        # Update sufficient statistics
        self.A *= g
        self.A += x @ x.T
        self.b *= g
        self.b += float(r) * x


# ---------------------------------------------------------------------
# Feature-hashing Encoder (deterministic, no randomness)
# ---------------------------------------------------------------------
class NeuralLinearArmManager:
    """
    Manages the neural-linear system's shared encoder.
    Provides a deterministic feature-hashing encoder of fixed dimensionality.
    The last coordinate is reserved for a bias term (1.0).
    """

    _instance: NeuralLinearArmManager | None = None

    # === Compatibility helpers for explanation paths ===

    def list_arms(self):
        """
        Best-effort list of arm IDs known to the manager.
        Tries several common attributes and falls back to discovered heads mapping.
        """
        ids = (
            getattr(self, "arm_ids", None)
            or getattr(self, "_arm_ids", None)
            or getattr(self, "arms", None)
            or getattr(self, "_arms", None)
        )
        # Normalize possible structures
        if isinstance(ids, list | tuple) and ids and all(isinstance(x, str) for x in ids):
            return list(ids)
        if isinstance(ids, list | tuple) and ids and hasattr(ids[0], "id"):
            return [a.id for a in ids]
        heads = self._ensure_heads_mapping()
        if heads:
            return list(heads.keys())
        return []

    def _ensure_heads_mapping(self):
        """
        Ensure we have a dict mapping arm_id -> linear head object.
        Works across multiple internal layouts:
        - dict attributes: _heads, heads, arm_heads, linear_heads, _linear_heads
        - sequence attributes zipped with arm id lists
        - lazily cached into self._heads
        Returns {} if nothing can be found (callers must handle gracefully).
        """
        # 1) Already present
        existing = getattr(self, "_heads", None)
        if isinstance(existing, dict) and existing:
            return existing

        # 2) Direct dict attributes
        for name in ("_heads", "heads", "arm_heads", "linear_heads", "_linear_heads"):
            val = getattr(self, name, None)
            if isinstance(val, dict) and val:
                setattr(self, "_heads", val)
                return val

        # 3) Sequence attributes + arm ids
        seq_candidates = []
        for name in (
            "heads",
            "arm_heads",
            "linear_heads",
            "_linear_heads",
            "models",
            "_models",
            "per_arm",
            "_per_arm",
        ):
            val = getattr(self, name, None)
            if isinstance(val, list | tuple) and val:
                seq_candidates.append(val)

        arm_ids = (
            getattr(self, "arm_ids", None)
            or getattr(self, "_arm_ids", None)
            or ([a.id for a in getattr(self, "arms", [])] if getattr(self, "arms", None) else None)
            or (
                [a.id for a in getattr(self, "_arms", [])] if getattr(self, "_arms", None) else None
            )
        )
        if arm_ids and isinstance(arm_ids, list | tuple):
            for seq in seq_candidates:
                if len(seq) == len(arm_ids):
                    mapping = {aid: head for aid, head in zip(arm_ids, seq)}
                    setattr(self, "_heads", mapping)
                    return mapping

        # 4) Nothing discoverable
        setattr(self, "_heads", {})
        return {}

    def get_theta_mean_for_arm(self, arm_id: str):
        """
        Return posterior mean vector θ for the arm.
        - Tolerates many internal layouts (theta_mean/mu/mean or posterior stats).
        - Never raises: returns [] (or zero vector) if unavailable so explanation never fails.
        """
        heads = self._ensure_heads_mapping()
        head = heads.get(arm_id) if isinstance(heads, dict) else None

        # If we have a head object, probe common attrs
        if head is not None:
            for attr in ("theta_mean", "mu", "mean"):
                if hasattr(head, attr):
                    vec = getattr(head, attr)
                    try:
                        return vec.tolist()  # numpy/torch
                    except Exception:
                        try:
                            return list(vec)
                        except Exception:
                            pass

            # Try deriving from posterior stats
            try:
                import numpy as np  # local import; optional
            except Exception:
                np = None

            if np is not None and hasattr(head, "precision") and hasattr(head, "b"):
                try:
                    mu = np.linalg.solve(head.precision, head.b)
                    return mu.tolist()
                except Exception:
                    pass
            if np is not None and hasattr(head, "Sigma") and hasattr(head, "beta"):
                try:
                    mu = head.Sigma @ head.beta
                    return getattr(mu, "tolist", lambda: list(mu))()

                except Exception:
                    pass

        # No head found → synthesize a harmless default so explanation path proceeds
        # Try to guess dimensionality
        dim = None
        # From manager
        for name in ("feature_dim", "d", "latent_dim", "embed_dim"):
            val = getattr(self, name, None)
            if isinstance(val, int) and val > 0:
                dim = val
                break
        # From any available head
        if dim is None and isinstance(heads, dict) and heads:
            sample = next(iter(heads.values()))
            for attr in ("theta_mean", "mu", "mean"):
                if hasattr(sample, attr):
                    try:
                        dim = len(getattr(sample, attr))
                    except Exception:
                        pass
                    break

        if isinstance(dim, int) and dim > 0:
            return [0.0] * dim
        return []  # final fallback

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Dimensionality can be configured via ENV; default 64.
        dim_env = os.getenv("NEURAL_LINEAR_ENCODER_DIM", "")
        try:
            d = int(dim_env) if dim_env else 64
        except Exception:
            d = 64
        self._encoder_dimensions = max(8, d)
        self._salt = os.getenv("NEURAL_LINEAR_HASH_SALT", "ecodia_synapse_v1").encode("utf-8")
        logger.info("[NeuralLinear] Manager initialized (dims=%d).", self._encoder_dimensions)

    @property
    def dimensions(self) -> int:
        return self._encoder_dimensions

    def _hidx(self, token: str) -> int:
        """
        Hash a token to an index in [0, dims-2]; dims-1 is reserved for bias.
        """
        h = hashlib.sha256(self._salt + token.encode("utf-8")).digest()
        # Use first 8 bytes as unsigned integer
        idx = int.from_bytes(h[:8], "little") % max(1, (self._encoder_dimensions - 1))
        return idx

    def encode(self, raw_context: dict[str, Any]) -> np.ndarray:
        """
        Encode a raw context dictionary into a (d,1) feature vector using feature hashing.
        - Numeric values contribute value-weighted features.
        - Strings/bools contribute 1.0 features.
        - Missing/None values are ignored.
        - Last index is a bias term set to 1.0.
        """
        d = self._encoder_dimensions
        vec = np.zeros((d, 1), dtype=np.float64)

        if raw_context:
            for k, v in raw_context.items():
                if v is None:
                    continue
                try:
                    if isinstance(v, int | float) and math.isfinite(float(v)):
                        token = f"{k}="
                        idx = self._hidx(token)
                        vec[idx, 0] += float(v)
                    else:
                        token = f"{k}={str(v)}"
                        idx = self._hidx(token)
                        vec[idx, 0] += 1.0
                except Exception:
                    # Defensive: skip any pathological value
                    continue

        # Bias feature
        vec[d - 1, 0] = 1.0
        return vec


# Singleton export
neural_linear_manager = NeuralLinearArmManager()
