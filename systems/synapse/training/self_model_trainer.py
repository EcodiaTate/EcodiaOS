# systems/synapse/training/self_model_trainer.py
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)


def _risk_score(val: Any) -> float:
    s = str(val or "").lower()
    if s.startswith("h"):
        return 1.0
    if s.startswith("l"):
        return 0.0
    return 0.5


def _budget_score(val: Any) -> float:
    s = str(val or "").lower()
    if "constrained" in s or "cheap" in s or "low" == s:
        return 0.0
    if "premium" in s or "expensive" in s or "high" == s:
        return 1.0
    return 0.5


def _safe_len(v: Any) -> int:
    try:
        return len(v) if hasattr(v, "__len__") else int(v)
    except Exception:
        return 0


def _vectorize_context(ctx: dict[str, Any]) -> list[float]:
    """
    Robust, schema-tolerant featureization of episode context.
    """
    risk = _risk_score(ctx.get("risk_level"))
    budget = _budget_score(ctx.get("budget"))
    cost_units = float(ctx.get("cost_units", 0.0) or 0.0)
    goal_len = float(_safe_len(ctx.get("goal")))
    task_key_len = float(_safe_len(ctx.get("task_key")))
    # Light transforms
    return [
        risk,
        budget,
        cost_units,
        np.log1p(goal_len),
        np.log1p(task_key_len),
    ]


def _build_dataset(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert cypher rows into (X, Y).
    X = concat(initial_state, context_features)
    Y = next_state
    """
    X_list: list[list[float]] = []
    Y_list: list[list[float]] = []

    for r in rows:
        init = r.get("initial_state")
        nxt = r.get("next_state")
        ctx = r.get("episode_context") or {}

        if not isinstance(init, list | tuple) or not isinstance(nxt, list | tuple):
            continue
        if len(init) == 0 or len(nxt) == 0:
            continue

        try:
            init_vec = [float(x) for x in init]
            next_vec = [float(x) for x in nxt]
        except Exception:
            continue

        xf = init_vec + _vectorize_context(ctx)
        X_list.append(xf)
        Y_list.append(next_vec)

    if not X_list:
        return np.zeros((0, 0), dtype=float), np.zeros((0, 0), dtype=float)

    # Pad/truncate Y vectors to a consistent dimension (use median length)
    lengths = [len(y) for y in Y_list]
    d_out = int(np.median(lengths))

    def _pad(v: list[float], d: int) -> list[float]:
        if len(v) >= d:
            return v[:d]
        return v + [0.0] * (d - len(v))

    Y_arr = np.asarray([_pad(y, d_out) for y in Y_list], dtype=float)
    X_arr = np.asarray(X_list, dtype=float)
    return X_arr, Y_arr


def _standardize(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Standardize features to zero mean / unit variance; returns (Xz, mean, std).
    std floors at small epsilon to avoid division by zero.
    """
    if X.size == 0:
        return X, np.zeros((0,), dtype=float), np.ones((0,), dtype=float)
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std < 1e-8, 1.0, std)
    Xz = (X - mean) / std
    return Xz, mean, std


def _ridge_fit(X: np.ndarray, Y: np.ndarray, l2: float = 1e-2) -> tuple[np.ndarray, np.ndarray]:
    """
    Solve multi-output ridge regression with bias by augmenting X with 1s.
    Returns (W, b) where Y ≈ X @ W + b
    """
    if X.size == 0 or Y.size == 0:
        return np.zeros((X.shape[1], 0), dtype=float), np.zeros((Y.shape[1],), dtype=float)

    # Augment with bias column
    ones = np.ones((X.shape[0], 1), dtype=float)
    Xa = np.hstack([X, ones])  # (n, d+1)

    d_plus = Xa.shape[1]
    I = np.eye(d_plus, dtype=float)
    I[-1, -1] = 0.0  # do not regularize bias

    # Normal equations: (Xa^T Xa + l2 I) θ = Xa^T Y
    A = Xa.T @ Xa + l2 * I
    B = Xa.T @ Y
    theta = np.linalg.solve(A, B)  # (d+1, k)

    W = theta[:-1, :]
    b = theta[-1, :]
    return W, b


def _metrics(Y_true: np.ndarray, Y_pred: np.ndarray) -> dict[str, float]:
    if Y_true.size == 0:
        return {"mse": 0.0, "r2": 0.0, "n": 0.0}
    err = Y_true - Y_pred
    mse = float(np.mean(err**2))
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((Y_true - Y_true.mean(axis=0)) ** 2))
    r2 = 0.0 if ss_tot <= 1e-12 else float(1.0 - ss_res / ss_tot)
    return {"mse": mse, "r2": r2, "n": float(Y_true.shape[0])}


async def _persist_model(
    W: np.ndarray,
    b: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
    dims_in: int,
    dims_out: int,
    metrics: dict[str, float],
) -> None:
    """
    Versioned upsert of the trained self-transition model.
    """
    await cypher_query(
        """
        MATCH (m:EquorSelfModel)
        WITH coalesce(max(m.version), 0) AS v
        CREATE (new:EquorSelfModel {
            id: 'self_model',
            version: v + 1,
            created_at: datetime(),
            dims_in: $dims_in,
            dims_out: $dims_out,
            weights: $W,
            bias: $b,
            norm: {mean: $mean, std: $std},
            metrics: $metrics
        })
        """,
        {
            "dims_in": int(dims_in),
            "dims_out": int(dims_out),
            "W": W.astype(float).T.tolist(),  # store as row-major (out x in)
            "b": b.astype(float).tolist(),
            "mean": mean.astype(float).tolist(),
            "std": std.astype(float).tolist(),
            "metrics": {k: float(v) for k, v in metrics.items()},
        },
    )


class SelfModelTrainer:
    """
    Trains the predictive model for Equor's self-awareness, learning the
    relationship between actions and resulting subjective states.
    """

    _instance: SelfModelTrainer | None = None
    _lock: asyncio.Lock

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def _fetch_training_data(self, limit: int = 5000) -> list[dict[str, Any]]:
        """
        Fetch sequences of (State, Context) -> Next_State from the graph.
        """
        query = """
        MATCH (e1:Episode)-[:EXPERIENCED]->(qs1:QualiaState)
        MATCH (e2:Episode)-[:EXPERIENCED]->(qs2:QualiaState)
        WHERE e1.task_key = e2.task_key AND e2.created_at > e1.created_at
        WITH e1, qs1, e2, qs2
        ORDER BY e2.created_at ASC
        WITH e1, qs1, head(collect(qs2)) AS next_qs
        RETURN qs1.manifold_coordinates AS initial_state,
               e1.context AS episode_context,
               next_qs.manifold_coordinates AS next_state
        ORDER BY e1.created_at DESC
        LIMIT $limit
        """
        rows = await cypher_query(query, {"limit": limit}) or []
        return rows if isinstance(rows, list) else []

    async def train_cycle(self):
        """
        Runs a full training cycle for the self-model:
          - fetch data
          - build dataset
          - standardize features
          - fit ridge model
          - evaluate
          - persist versioned parameters
        """
        if self._lock.locked():
            logger.info("[SelfModelTrainer] Training already in progress; skipping.")
            return

        async with self._lock:
            logger.info(
                "[SelfModelTrainer] Starting training cycle for Equor's predictive self-model.",
            )
            rows = await self._fetch_training_data()

            n_rows = len(rows)
            if n_rows < 100:
                logger.info("[SelfModelTrainer] Insufficient sequence data (%d). Skipping.", n_rows)
                return

            X, Y = _build_dataset(rows)
            if X.size == 0 or Y.size == 0:
                logger.info("[SelfModelTrainer] No valid samples after preprocessing. Skipping.")
                return

            # Train/val split (80/20), deterministic
            n = X.shape[0]
            idx = np.arange(n)
            rng = np.random.default_rng(2025)
            rng.shuffle(idx)
            split = int(0.8 * n)
            train_idx, val_idx = idx[:split], idx[split:]

            X_tr, Y_tr = X[train_idx], Y[train_idx]
            X_va, Y_va = X[val_idx], Y[val_idx]

            # Standardize using train statistics only
            Xz_tr, mean, std = _standardize(X_tr)
            Xz_va = (X_va - mean) / std

            # Fit ridge
            W, b = _ridge_fit(Xz_tr, Y_tr, l2=1e-2)

            # Evaluate
            Y_pred_va = Xz_va @ W + b
            m = _metrics(Y_va, Y_pred_va)
            m.update({"n_train": float(X_tr.shape[0]), "n_val": float(X_va.shape[0])})

            # Persist (input dims exclude bias; include context features)
            dims_in = int(X.shape[1])
            dims_out = int(Y.shape[1])
            await _persist_model(W, b, mean, std, dims_in, dims_out, m)

            logger.info(
                "[SelfModelTrainer] Training complete. n=%d val_mse=%.6f val_r2=%.3f",
                int(m["n_train"] + m["n_val"]),
                float(m["mse"]),
                float(m["r2"]),
            )


# Singleton export
self_model_trainer = SelfModelTrainer()
