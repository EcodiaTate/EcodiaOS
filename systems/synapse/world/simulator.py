# systems/synapse/world/simulator.py
# FINAL VERSION - Learned World Model (singleton, instance-safe)
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from pydantic import BaseModel

from systems.synapse.policy.policy_dsl import PolicyGraph
from systems.synapse.schemas import TaskContext
from systems.synapse.training.neural_linear import neural_linear_manager

MODEL_STORE_PATH = Path(os.getenv("SYNAPSE_MODEL_STORE", "/app/.synapse/models/"))
WORLD_MODEL_PATH = MODEL_STORE_PATH / "world_model_v1.joblib"


class SimulationPrediction(BaseModel):
    p_success: float = 0.5
    delta_cost: float = 0.0
    p_safety_hit: float = 0.1
    # Sigma reflects model confidence/dispersion, not a direct output
    sigma: float = 0.5


class WorldModel:
    """
    Counterfactual world model that predicts outcomes of policy graphs
    using a learned model trained on historical data.
    Singleton: use `world_model` exported at bottom.
    """

    _instance: WorldModel | None = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            # Instance-scoped state
            inst._vectorizer = None  # type: ignore[attr-defined]
            inst._models: list[Any] = []  # type: ignore[attr-defined]
            # Load artifact on the instance
            inst.load_model()
            cls._instance = inst
        return cls._instance

    # Keep as instance method; we call it on the instance in __new__
    def load_model(self) -> None:
        """Load the latest trained world-model artifact from disk (if present)."""
        if WORLD_MODEL_PATH.exists():
            try:
                data = joblib.load(WORLD_MODEL_PATH)
                self._vectorizer = data.get("vectorizer", None)
                self._models = list(data.get("models", []) or [])
                print(f"[WorldModel] Loaded learned model artifact from {WORLD_MODEL_PATH}")
            except Exception as e:
                print(
                    f"[WorldModel] WARNING: Could not load model artifact: {e}. Falling back to heuristics.",
                )
                self._vectorizer = None
                self._models = []
        else:
            print("[WorldModel] No learned model artifact found. Falling back to heuristics.")
            self._vectorizer = None
            self._models = []

    def _featurize(self, task_ctx: TaskContext) -> dict[str, float]:
        """Create feature dictionary for prediction. Must match trainer featurization."""
        context_vec = neural_linear_manager.encode(task_ctx.model_dump())
        # Flatten to 1D and name features deterministically
        flat = np.ravel(context_vec).astype(float).tolist()
        return {f"ctx_{i}": v for i, v in enumerate(flat)}

    @staticmethod
    def _safe_sigma_from_models(models: list[Any], X: Any) -> float:
        """
        Estimate uncertainty as average stddev across base estimators if available.
        Falls back to a small constant if the model type doesn't expose estimators.
        """
        try:
            per_model_sigmas: list[float] = []
            for m in models:
                ests = getattr(m, "estimators_", None)
                if ests:
                    preds = []
                    for est in ests:
                        # Some estimators expect ndarray[float32]; be permissive
                        try:
                            preds.append(float(est.predict(X)))
                        except Exception:
                            preds.append(float(est.predict(X.astype(np.float32))))
                    if preds:
                        per_model_sigmas.append(float(np.std(preds)))
            if per_model_sigmas:
                return float(np.mean(per_model_sigmas))
        except Exception:
            pass
        return 0.5  # conservative default

    async def simulate(
        self,
        plan_graph: PolicyGraph,
        task_ctx: TaskContext,
    ) -> SimulationPrediction:
        """
        Predict outcome by running the featurized context through the learned models.
        Falls back to a simple heuristic when no artifact is loaded.
        """
        if not getattr(self, "_models", None) or not getattr(self, "_vectorizer", None):
            # Heuristic fallback when no model is available
            return SimulationPrediction(
                p_success=0.6 if getattr(task_ctx, "risk_level", "") != "high" else 0.45,
                delta_cost=0.0,
                p_safety_hit=0.5 if getattr(task_ctx, "risk_level", "") == "high" else 0.1,
                sigma=0.6 if getattr(task_ctx, "risk_level", "") == "high" else 0.4,
            )

        # Vectorize features
        features = self._featurize(task_ctx)
        X = self._vectorizer.transform([features])

        # Predict each output dimension with its corresponding model
        try:
            preds = [float(model.predict(X)[0]) for model in self._models]
        except Exception as e:
            print(f"[WorldModel] Prediction error ({e}); falling back to heuristic.")
            return SimulationPrediction(
                p_success=0.55,
                delta_cost=0.0,
                p_safety_hit=0.15,
                sigma=0.5,
            )

        # Unpack with defensive defaults
        p_success = float(np.clip(preds[0] if len(preds) > 0 else 0.55, 0.0, 1.0))
        delta_cost = float(
            -(preds[1] if len(preds) > 1 else 0.0),
        )  # model predicts negative cost → invert
        p_safety_hit = float(
            np.clip(-(preds[2] if len(preds) > 2 else -0.15), 0.0, 1.0),
        )  # invert if trained that way

        sigma = self._safe_sigma_from_models(self._models, X)

        pred = SimulationPrediction(
            p_success=p_success,
            delta_cost=delta_cost,
            p_safety_hit=p_safety_hit,
            sigma=sigma,
        )

        try:
            phash = getattr(plan_graph, "canonical_hash", None)
            tag = phash[:8] if isinstance(phash, str) else "unknown"
        except Exception:
            tag = "unknown"

        print(f"[WorldModel] Predicted outcome for policy {tag}: {pred.model_dump()}")
        return pred


# Singleton export
world_model = WorldModel()
