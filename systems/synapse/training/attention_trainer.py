# systems/synapse/training/attention_trainer.py
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import numpy as np

from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    # Stable sigmoid
    z = np.clip(z, -40, 40)
    return 1.0 / (1.0 + np.exp(-z))


def _vectorize_cognit(c: dict[str, Any]) -> list[float]:
    """
    Robust feature vectorization for a 'cognit'.
    Fields tolerated:
      - salience: float
      - source_process: str (contains 'Critic' → binary)
      - content: str (length proxy)
    """
    sal = float(c.get("salience", 0.0) or 0.0)
    src = str(c.get("source_process", "") or "")
    cnt = c.get("content", "")
    length = float(
        len(cnt) if isinstance(cnt, str) else int(cnt) if isinstance(cnt, int | float) else 0,
    )

    # Simple transforms
    sal_sqrt = math.sqrt(max(0.0, sal))
    len_log = math.log1p(max(0.0, length))

    is_critic = 1.0 if "critic" in src.lower() else 0.0

    # Add bias as final term during training (intercept handled separately)
    return [sal, sal_sqrt, len_log, is_critic]


def _build_samples(delibs: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert deliberation rows into (X, y).
    Positive labels when APPROVE with high confidence.
    Negatives derived from:
      - explicit non-selected candidates if available (preferred),
      - or from low-confidence APPROVE/REJECT as 0 labels for chosen.
    """
    X: list[list[float]] = []
    y: list[int] = []

    for d in delibs:
        outcome = str(d.get("final_outcome", "") or "").upper()
        confidence = float(d.get("final_confidence", 0.0) or 0.0)
        ignitions = d.get("ignitions") or []

        # Define label rule
        pos_label = 1 if (outcome == "APPROVE" and confidence >= 0.75) else 0

        for ignition in ignitions:
            chosen = ignition.get("selected_cognit") or {}
            # Always include chosen sample with label rule
            X.append(_vectorize_cognit(chosen))
            y.append(pos_label)

            # If candidates provided, create negatives from non-selected
            cands = ignition.get("candidates") or []
            if isinstance(cands, list) and cands:
                for cand in cands:
                    # Skip the chosen if present in candidates list
                    if cand is chosen:
                        continue
                    X.append(_vectorize_cognit(cand))
                    # Mirror label: if chosen is positive, others are negative; else keep 0
                    y.append(0)

    if not X:
        return np.zeros((0, 4), dtype=float), np.zeros((0,), dtype=int)

    return np.asarray(X, dtype=float), np.asarray(y, dtype=int)


def _train_logreg(
    X: np.ndarray,
    y: np.ndarray,
    l2: float = 1e-2,
    lr: float = 0.05,
    epochs: int = 200,
    batch_size: int = 128,
    seed: int = 13,
) -> tuple[np.ndarray, float, dict[str, float]]:
    """
    L2-regularized logistic regression with mini-batch gradient descent.
    Returns (weights, intercept, metrics)
    """
    rng = np.random.default_rng(seed)
    n, d = X.shape
    w = rng.normal(scale=0.01, size=(d,))
    b = 0.0

    def batch_iter():
        idx = np.arange(n)
        rng.shuffle(idx)
        for i in range(0, n, batch_size):
            sl = idx[i : i + batch_size]
            yield X[sl], y[sl]

    for _ in range(epochs):
        for xb, yb in batch_iter():
            z = xb @ w + b
            p = _sigmoid(z)
            # gradients
            err = p - yb
            grad_w = (xb.T @ err) / xb.shape[0] + l2 * w
            grad_b = float(np.sum(err) / xb.shape[0])
            # update
            w -= lr * grad_w
            b -= lr * grad_b

    # Metrics (simple)
    with np.errstate(divide="ignore", invalid="ignore"):
        logits = X @ w + b
        probs = _sigmoid(logits)
    preds = (probs >= 0.5).astype(int)
    acc = float(np.mean(preds == y)) if n > 0 else 0.0
    pos_rate = float(np.mean(y)) if n > 0 else 0.0
    return w, b, {"accuracy": acc, "positives": pos_rate, "n_samples": float(n)}


async def _persist_model(weights: list[float], bias: float, metrics: dict[str, float]) -> None:
    """
    Versioned upsert of the trained attention ranker parameters into the graph.
    """
    await cypher_query(
        """
        MATCH (m:UnityAttentionRanker)
        WITH coalesce(max(m.version), 0) AS v
        CREATE (new:UnityAttentionRanker {
            id: 'attention_ranker',
            version: v + 1,
            created_at: datetime(),
            weights: $weights,
            bias: $bias,
            metrics: $metrics
        })
        """,
        {"weights": [float(w) for w in weights], "bias": float(bias), "metrics": metrics},
    )


class AttentionRankerTrainer:
    """
    Trains a ranking model to determine which 'Cognit' in the Global
    Workspace is most important. Learns from the outcomes of past deliberations.
    """

    _instance: AttentionRankerTrainer | None = None
    _lock: asyncio.Lock

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def _fetch_training_data(self, limit: int = 1000) -> list[dict[str, Any]]:
        """
        Fetch historical attention choices and resulting deliberation outcomes.
        Expects ignition events in the episode audit.
        """
        query = """
        MATCH (d:Deliberation)-[:RESULTED_IN]->(v:Verdict)
        MATCH (e:Episode {deliberation_id: d.id})
        WHERE e.audit_trace.ignition_events IS NOT NULL
        RETURN e.audit_trace.ignition_events AS ignitions,
               v.outcome AS final_outcome,
               v.confidence AS final_confidence
        ORDER BY e.created_at DESC
        LIMIT $limit
        """
        rows = await cypher_query(query, {"limit": limit}) or []
        if not isinstance(rows, list):
            return []
        # Normalize shapes just in case
        normed: list[dict[str, Any]] = []
        for r in rows:
            ign = r.get("ignitions") or []
            if not isinstance(ign, list):
                ign = []
            normed.append(
                {
                    "ignitions": ign,
                    "final_outcome": r.get("final_outcome"),
                    "final_confidence": r.get("final_confidence"),
                },
            )
        return normed

    def _create_training_samples(self, deliberations: list[dict[str, Any]]):
        """
        Build feature matrix and labels for the ranker.
        """
        return _build_samples(deliberations)

    async def train_cycle(self):
        """
        Run a full training cycle for the attention ranking model.
        - Fetch data
        - Build samples
        - Fit L2 logistic regression
        - Persist weights & metrics
        """
        if self._lock.locked():
            logger.info("[AttentionTrainer] Training already in progress; skipping.")
            return

        async with self._lock:
            logger.info("[AttentionTrainer] Starting training cycle for Unity's attention ranker.")
            deliberation_data = await self._fetch_training_data()

            n_rows = len(deliberation_data)
            if n_rows < 50:
                logger.info(
                    "[AttentionTrainer] Insufficient deliberation data (%d). Skipping.",
                    n_rows,
                )
                return

            X, y = self._create_training_samples(deliberation_data)
            if X.size == 0:
                logger.info("[AttentionTrainer] No valid training samples extracted. Skipping.")
                return

            # Shuffle once deterministically for reproducibility
            rng = np.random.default_rng(42)
            idx = np.arange(X.shape[0])
            rng.shuffle(idx)
            X, y = X[idx], y[idx]

            # Fit
            w, b, metrics = _train_logreg(
                X,
                y,
                l2=1e-2,
                lr=0.05,
                epochs=200,
                batch_size=128,
                seed=42,
            )

            # Persist
            await _persist_model(weights=w.tolist(), bias=b, metrics=metrics)
            logger.info(
                "[AttentionTrainer] Training complete. samples=%d acc=%.3f pos_rate=%.3f",
                int(metrics.get("n_samples", 0)),
                float(metrics.get("accuracy", 0.0)),
                float(metrics.get("positives", 0.0)),
            )


# Singleton export
attention_trainer = AttentionRankerTrainer()
