from __future__ import annotations

import asyncio
import logging
from typing import List

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry_bootstrap import ArmFamilyConfig, ArmStrategyTemplate, ArmVariant
from systems.synapse.policy.policy_dsl import LLMParamsEffect, PolicyGraph, PolicyNode

logger = logging.getLogger(__name__)

# Optional default grid for this family (kept small)
DEFAULT_MODELS = ["gpt-4o", "gpt-3.5-turbo", "gemini-2.0-pro"]
DEFAULT_TEMPS = [0.1, 0.4, 0.7, 1.1, 1.5]
DEFAULT_TOKENS = [1024, 2048, 4096]


async def ensure_base_family_schema() -> None:
    """
    Graph-side seed so the registry can be fully graph-driven.
    Safe to omit if you prefer fallback-only behavior.
    """
    # Family
    await cypher_query("""
    MERGE (f:ArmFamily {family_id: "base"})
    ON CREATE SET f.mode = "generic", f.base_tags = ["general", "generic", "base"]
    """)

    # Minimal grid (optional; keeps future flexibility)
    for m in DEFAULT_MODELS:
        await cypher_query(
            """
        MERGE (m:Model {name: $m})
        WITH m
        MERGE (f:ArmFamily {family_id: "base"})
        MERGE (f)-[:USES_MODEL]->(m)
        """,
            {"m": m},
        )

    for t in DEFAULT_TEMPS:
        await cypher_query(
            """
        MERGE (t:Temperature {value: $t})
        WITH t
        MERGE (f:ArmFamily {family_id: "base"})
        MERGE (f)-[:USES_TEMPERATURE]->(t)
        """,
            {"t": t},
        )

    for k in DEFAULT_TOKENS:
        await cypher_query(
            """
        MERGE (k:TokenLimit {value: $k})
        WITH k
        MERGE (f:ArmFamily {family_id: "base"})
        MERGE (f)-[:USES_TOKENS]->(k)
        """,
            {"k": k},
        )

    # Strategy: "params" (matches your legacy behavior)
    await cypher_query("""
    MERGE (f:ArmFamily {family_id: "base"})
    MERGE (f)-[:HAS_STRATEGY]->(s:StrategyTemplate {name: "params"})
    """)


async def _load_base_strategies() -> list[ArmStrategyTemplate]:
    rows = (
        await cypher_query("""
    MATCH (f:ArmFamily {family_id: "base"})-[:HAS_STRATEGY]->(s:StrategyTemplate)
    RETURN s.name AS name, s.tags AS tags
    """)
        or []
    )
    return [
        ArmStrategyTemplate(name=r["name"], tags=r.get("tags", [])) for r in rows if r.get("name")
    ]


async def _strategy_templates_fn() -> list[ArmStrategyTemplate]:
    """
    Async entrypoint used by the registry. The bootstrapper should await this.
    Falls back to a single 'params' template if the graph is empty.
    """
    strategies = await _load_base_strategies()
    return strategies or [ArmStrategyTemplate(name="params")]


def _build_params_only_graph(arm_id: str, variant: ArmVariant) -> PolicyGraph:
    return PolicyGraph(
        id=arm_id,
        version=1,  # keep version stable for compatibility
        nodes=[PolicyNode(id="prompt", type="prompt", model=variant.model)],
        effects=[
            LLMParamsEffect(
                model=variant.model,
                temperature=variant.temperature,
                max_tokens=variant.max_tokens,
            )
        ],
    )


# Exported family:
# - strategy_templates_fn is ASYNC and must be awaited by the registry bootstrapper.
BASE_FAMILY = ArmFamilyConfig(
    family_id="base",
    mode="generic",
    base_tags=["general", "generic", "base"],
    strategy_templates_fn=_strategy_templates_fn,  # <-- awaited by caller
    policy_builder_fn=_build_params_only_graph,
)
