# systems/synapse/core/meta_controller.py
from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.schemas import TaskContext

logger = logging.getLogger(__name__)

CognitiveMode = Literal["greedy", "reflective", "planful", "consensus"]

# Deterministic defaults (used only if graph/env absent)
DEFAULT_STRATEGY_MAP: dict[str, dict[str, Any]] = {
    "low": {"cognitive_mode": "greedy", "critic_blend": 0.10, "reflection_depth": 0},
    "medium": {"cognitive_mode": "reflective", "critic_blend": 0.30, "reflection_depth": 1},
    "high": {"cognitive_mode": "planful", "critic_blend": 0.60, "reflection_depth": 2},
}
DEFAULT_BUDGET_MAP: dict[str, dict[str, int]] = {
    "low": {"tokens": 4096, "cost_units": 1},
    "medium": {"tokens": 8192, "cost_units": 3},
    "high": {"tokens": 16384, "cost_units": 10},
}


def _load_json_env(name: str) -> dict[str, Any] | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        logger.warning("Failed to parse %s from environment.", name, exc_info=True)
        return None


def _validate_strategy_map(m: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for risk in ("low", "medium", "high"):
        src = m.get(risk, {})
        base = DEFAULT_STRATEGY_MAP[risk].copy()
        if isinstance(src, dict):
            base.update(
                {
                    "cognitive_mode": src.get("cognitive_mode", base["cognitive_mode"]),
                    "critic_blend": float(src.get("critic_blend", base["critic_blend"])),
                    "reflection_depth": int(src.get("reflection_depth", base["reflection_depth"])),
                },
            )
        out[risk] = base
    return out


def _validate_budget_map(m: dict[str, Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for risk in ("low", "medium", "high"):
        src = m.get(risk, {})
        base = DEFAULT_BUDGET_MAP[risk].copy()
        if isinstance(src, dict):
            base.update(
                {
                    "tokens": int(src.get("tokens", base["tokens"])),
                    "cost_units": int(src.get("cost_units", base["cost_units"])),
                },
            )
        out[risk] = base
    return out


class MetaController:
    """
    Meta-cognitive control plane:
      - Strategy selection (mode, critic blend, reflection depth)
      - Budget allocation (tokens, cost_units)
    Maps are sourced in priority order: Graph → Environment → Defaults.
    """

    _instance: MetaController | None = None
    _strategy_map: dict[str, dict[str, Any]] = _validate_strategy_map(DEFAULT_STRATEGY_MAP)
    _budget_map: dict[str, dict[str, int]] = _validate_budget_map(DEFAULT_BUDGET_MAP)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self) -> None:
        """
        Load optimized maps from the graph; fallback to env if graph empty/unavailable.
        Env variables (JSON objects):
          SYNAPSE_STRATEGY_MAP, SYNAPSE_BUDGET_MAP
        """
        try:
            # Strategy from graph
            rows = await cypher_query(
                """
                MATCH (c:SynapseHyperparameters)
                RETURN c.strategy_map AS strategy_map
                ORDER BY c.version DESC
                LIMIT 1
                """,
            )
            loaded_strategy = None
            if rows and rows[0].get("strategy_map") is not None:
                sm = rows[0]["strategy_map"]
                loaded_strategy = json.loads(sm) if isinstance(sm, str) else sm

            # Budget from graph
            rows_b = await cypher_query(
                """
                MATCH (b:BudgetPolicy)
                RETURN b.map AS map
                ORDER BY b.version DESC
                LIMIT 1
                """,
            )
            loaded_budget = None
            if rows_b and rows_b[0].get("map") is not None:
                bm = rows_b[0]["map"]
                loaded_budget = json.loads(bm) if isinstance(bm, str) else bm

            # Env fallbacks if graph omitted either map
            if loaded_strategy is None:
                loaded_strategy = _load_json_env("SYNAPSE_STRATEGY_MAP")
            if loaded_budget is None:
                loaded_budget = _load_json_env("SYNAPSE_BUDGET_MAP")

            # Validate + set
            if loaded_strategy:
                self._strategy_map = _validate_strategy_map(loaded_strategy)
                logger.info("[MetaController] Strategy map loaded.")
            else:
                self._strategy_map = _validate_strategy_map(DEFAULT_STRATEGY_MAP)
                logger.warning("[MetaController] Strategy map defaulted.")

            if loaded_budget:
                self._budget_map = _validate_budget_map(loaded_budget)
                logger.info("[MetaController] Budget map loaded.")
            else:
                self._budget_map = _validate_budget_map(DEFAULT_BUDGET_MAP)
                logger.warning("[MetaController] Budget map defaulted.")

        except Exception:
            # Hard fallback to defaults if any error occurred
            self._strategy_map = _validate_strategy_map(DEFAULT_STRATEGY_MAP)
            self._budget_map = _validate_budget_map(DEFAULT_BUDGET_MAP)
            logger.exception("[MetaController] Graph initialization failed; using defaults.")

    def select_strategy(self, request: TaskContext) -> dict[str, Any]:
        """Select a cognitive strategy based on risk level."""
        risk = getattr(request, "risk_level", "medium")
        strat = self._strategy_map.get(risk) or self._strategy_map["medium"]
        logger.debug("[MetaController] risk=%s strategy=%s", risk, strat)
        return strat

    def allocate_budget(self, request: TaskContext) -> dict[str, int]:
        """Allocate tokens and cost units based on risk level."""
        risk = getattr(request, "risk_level", "medium")
        budget = self._budget_map.get(risk) or self._budget_map["medium"]
        logger.debug("[MetaController] risk=%s budget=%s", risk, budget)
        return budget


# Singleton export
meta_controller = MetaController()
