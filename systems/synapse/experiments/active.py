# systems/synapse/experiments/active.py
# FINAL, COMPLETE VERSION
from __future__ import annotations

import logging
import re
from typing import Any

from systems.synapse.schemas import TaskContext

logger = logging.getLogger(__name__)


def _risk_from_tokens(tokens: list[str], default: str = "medium") -> str:
    for t in tokens:
        lt = t.lower()
        if "high" in lt:
            return "high"
        if "low" in lt:
            return "low"
        if "medium" in lt:
            return "medium"
    return default


def _budget_from_tokens(tokens: list[str], default: str = "constrained") -> str:
    for t in tokens:
        lt = t.lower()
        if "constrained" in lt or "cheap" in lt or "low_cost" in lt:
            return "constrained"
        if "normal" in lt:
            return "normal"
        if "premium" in lt or "expensive" in lt or "high_cost" in lt:
            return "premium"
    return default


def _parse_niche_key(key: str) -> dict[str, Any] | None:
    """
    Support both forms:
      - "niche_(simula, high_risk, low_cost)"
      - "niche:simula:high_risk:low_cost"
    Returns dict with tokens list if matched.
    """
    k = key.strip()
    if k.startswith("niche_"):
        m = re.match(r"^niche_\((.*)\)$", k)
        if m:
            tokens = [t.strip(" '\"\t") for t in m.group(1).split(",") if t.strip()]
            return {"tokens": tokens}
    if k.startswith("niche:"):
        tokens = [t.strip() for t in k.split(":")[1:] if t.strip()]
        return {"tokens": tokens}
    return None


def _parse_sim_uncertainty_key(key: str) -> str | None:
    """
    Accept:
      - "simulator_uncertainty:<task_key>"
      - "simulator_uncertainty_<task_key>"
    Returns extracted task_key if matched.
    """
    if key.startswith("simulator_uncertainty:"):
        return key.split(":", 1)[1].strip()
    if key.startswith("simulator_uncertainty_"):
        return key.split("simulator_uncertainty_", 1)[1].strip()
    return None


class ExperimentDesigner:
    """
    Designs low-cost experiments to maximize information gain, creating an
    auto-curriculum for the system to follow. (H2, H20)
    """

    _instance: ExperimentDesigner | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def design_probe(self, uncertainty_map: dict[str, float]) -> TaskContext | None:
        """
        Given a map of the system's uncertainties, design a cheap probe action
        by generating a TaskContext for Simula to execute.

        Selection policy:
          1) Choose the highest-uncertainty key (ties break lexicographically).
          2) If it's a niche key, craft a targeted exploration probe.
          3) If it's simulator uncertainty, schedule a controlled re-run.
          4) Otherwise, fall back to a generic probe with conservative budget.
        """
        if not uncertainty_map:
            return None

        # Stable, deterministic selection with tie-breaking
        top_key = max(
            sorted(uncertainty_map.keys()),
            key=lambda k: float(uncertainty_map.get(k, 0.0)),
        )
        score = float(uncertainty_map.get(top_key, 0.0))
        logger.info(
            "[ExperimentDesigner] Selected probe target key='%s' uncertainty=%.6f",
            top_key,
            score,
        )

        # 1) Niche-directed exploration
        niche = _parse_niche_key(top_key)
        if niche is not None:
            tokens = niche["tokens"]
            risk = _risk_from_tokens(tokens, default="medium")
            budget = _budget_from_tokens(tokens, default="constrained")
            # Optional domain/topic hint (first token often a subsystem like 'simula')
            domain = tokens[0] if tokens else "system"

            return TaskContext(
                task_key="synapse_auto_curriculum_probe",
                goal=(
                    f"Explore under-sampled behavioral niche for '{domain}'. "
                    f"Prioritize information gain to reduce uncertainty labeled '{top_key}'."
                ),
                risk_level=risk,
                budget=budget,
            )

        # 2) Simulator-uncertainty re-run
        task_key = _parse_sim_uncertainty_key(top_key)
        if task_key:
            return TaskContext(
                task_key=f"synapse_auto_curriculum_repro_{task_key}",
                goal=(
                    f"Re-run task '{task_key}' with controlled context perturbations to reduce "
                    f"simulator uncertainty labeled '{top_key}'."
                ),
                risk_level="low",
                budget="normal",
            )

        # 3) Generic exploration probe
        return TaskContext(
            task_key="synapse_auto_curriculum_generic_probe",
            goal=f"Design a minimal-cost experiment to reduce uncertainty labeled '{top_key}'.",
            risk_level="medium",
            budget="constrained",
        )


# Singleton export
experiment_designer = ExperimentDesigner()
