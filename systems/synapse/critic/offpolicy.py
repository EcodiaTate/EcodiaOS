# systems/synapse/critic/offpolicy.py
# FINAL VERSION - REAL ML IMPLEMENTATION
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.schemas import TaskContext

# Define path for storing the trained model artifact
MODEL_STORE_PATH = Path(os.getenv("SYNAPSE_MODEL_STORE", "/app/.synapse/models/"))
MODEL_STORE_PATH.mkdir(parents=True, exist_ok=True)
CRITIC_MODEL_PATH = MODEL_STORE_PATH / "critic_v1.joblib"

# In-memory cache for the loaded model and vectorizer
CRITIC_MODEL: Any | None = None
CRITIC_VECTORIZER: DictVectorizer | None = None


def _featurize_episode(log: dict[str, Any]) -> dict[str, Any] | None:
    """
    Converts a raw episode log from Neo4j into a flat feature dictionary
    for the machine learning model.
    """
    context = log.get("context", {})
    audit = log.get("audit", {})
    if not context or not audit:
        return None

    features = {
        "risk_level_low": context.get("risk_level") == "low",
        "risk_level_medium": context.get("risk_level") == "medium",
        "risk_level_high": context.get("risk_level") == "high",
        "budget_constrained": context.get("budget") == "constrained",
        "budget_normal": context.get("budget") == "normal",
        "budget_extended": context.get("budget") == "extended",
        "num_candidates": len(audit.get("bandit_scores", [])),
        "firewall_fallback": audit.get("firewall", {}).get("safe_fallback", False),
    }
    return features


class Critic:
    """
    Manages the off-policy critic model. Learns from rich episode logs
    to predict the value of actions, enabling re-ranking and off-policy evaluation.
    """

    _instance: Critic | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        """Loads the latest critic model and vectorizer from disk."""
        global CRITIC_MODEL, CRITIC_VECTORIZER
        if CRITIC_MODEL_PATH.exists():
            try:
                data = joblib.load(CRITIC_MODEL_PATH)
                CRITIC_MODEL = data["model"]
                CRITIC_VECTORIZER = data["vectorizer"]
                print(f"[Critic] Loaded model artifact from {CRITIC_MODEL_PATH}")
            except Exception as e:
                print(f"[Critic] ERROR: Could not load model artifact: {e}")
                CRITIC_MODEL, CRITIC_VECTORIZER = None, None
        else:
            print("[Critic] No model artifact found. Critic will return neutral scores.")

    async def fetch_training_data(self, limit: int = 5000) -> list[dict[str, Any]]:
        """Fetches the rich episode logs needed to train the critic."""
        query = """
        MATCH (e:Episode)
        WHERE e.audit_trace IS NOT NULL AND e.reward IS NOT NULL
        RETURN e.context as context,
               e.reward as reward,
               e.audit_trace as audit
        ORDER BY e.created_at DESC
        LIMIT $limit
        """
        return await cypher_query(query, {"limit": limit}) or []

    async def fit_nightly(self):
        """
        Fits a new critic model on a batch of episode logs and saves it.
        This is a real ML training loop.
        """
        global CRITIC_MODEL, CRITIC_VECTORIZER
        logs = await self.fetch_training_data()
        if len(logs) < 100:
            print(
                f"[Critic] Insufficient data ({len(logs)} episodes) to train new model. Skipping.",
            )
            return

        print(f"[Critic] Fitting new model on {len(logs)} episode logs...")

        # 1. Featurize Data
        features = [_featurize_episode(log) for log in logs]
        rewards = [log.get("reward", 0.0) for log in logs]

        valid_indices = [i for i, f in enumerate(features) if f is not None]
        if not valid_indices:
            print("[Critic] No valid features could be extracted from logs. Skipping training.")
            return

        X_dicts = [features[i] for i in valid_indices]
        y = np.array([rewards[i] for i in valid_indices])

        # 2. Vectorize features and train model
        vectorizer = DictVectorizer(sparse=False)
        X = vectorizer.fit_transform(X_dicts)

        model = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=3,
            random_state=42,
        )
        model.fit(X, y)

        # 3. Version and save the model artifact atomically
        print(f"[Critic] Training complete. Saving model artifact to {CRITIC_MODEL_PATH}")
        model_payload = {"model": model, "vectorizer": vectorizer}

        temp_path = CRITIC_MODEL_PATH.with_suffix(".tmp")
        joblib.dump(model_payload, temp_path)
        temp_path.rename(CRITIC_MODEL_PATH)

        # 4. Load the new model into memory for immediate use
        CRITIC_MODEL = model
        CRITIC_VECTORIZER = vectorizer
        print("[Critic] New critic model is now live.")

    def score(self, task_ctx: TaskContext, arm_id: str) -> float:
        """
        Scores a given context for a specific arm using the current critic model.
        """
        if CRITIC_MODEL is None or CRITIC_VECTORIZER is None:
            self._load_model()
            if CRITIC_MODEL is None:  # If loading failed
                return 0.0

        # Featurize the current context
        # In the future, we would also add arm-specific features here
        features_dict = _featurize_episode(
            {
                "context": task_ctx.model_dump(),
                "audit": {"bandit_scores": [], "firewall": {}},  # Mock audit for featurization
            },
        )
        if not features_dict:
            return 0.0

        X = CRITIC_VECTORIZER.transform([features_dict])

        # Predict the expected reward
        predicted_reward = CRITIC_MODEL.predict(X)[0]
        return float(predicted_reward)

    async def rerank_topk(
        self,
        request: TaskContext,
        candidate_scores: dict[str, float],
        blend_factor: float = 0.3,  # Default blend, can be overridden by MetaController
    ) -> str:
        """
        Re-ranks the bandit's top candidates using the critic's predicted reward.
        Blends the bandit (exploration) and critic (exploitation) scores.
        """
        if not candidate_scores:
            raise ValueError("Cannot rerank an empty set of candidates.")

        if CRITIC_MODEL is None:
            print("[Critic] No model loaded, skipping re-ranking.")
            return max(candidate_scores, key=candidate_scores.get)

        blended_scores = {}
        for arm_id, bandit_score in candidate_scores.items():
            critic_score_val = self.score(request, arm_id)
            # Blend factor now dynamically controls critic influence
            blended_scores[arm_id] = (
                1.0 - blend_factor
            ) * bandit_score + blend_factor * critic_score_val

        reranked_champion_id = max(blended_scores, key=blended_scores.get)
        original_champion_id = max(candidate_scores, key=candidate_scores.get)

        if reranked_champion_id != original_champion_id:
            print(
                f"[Critic] Re-rank flipped champion from '{original_champion_id}' to '{reranked_champion_id}'.",
            )

        return reranked_champion_id


# Singleton export
critic = Critic()
