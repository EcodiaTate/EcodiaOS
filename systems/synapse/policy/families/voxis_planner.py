# COMPLETE REPLACEMENT - SIMPLE PER-FAMILY REGISTRY (GRAPH-DRIVEN)

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import yaml

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry_bootstrap import (
    ArmFamilyConfig,
    ArmStrategyTemplate,
    ArmVariant,
)
from systems.synapse.policy.policy_dsl import (
    LLMParamsEffect,
    PolicyGraph,
    PolicyNode,
    TagBiasEffect,
    ToolBiasEffect,
)

logger = logging.getLogger(__name__)

# ------------ Config -------------
CATALOG_PATH = "config/catalog.voxisTools.yaml"

# Default grid (ensured into graph for this family)
DEFAULT_MODELS = ["gpt-4o", "gpt-3.5-turbo", "gemini-2.0-pro"]
DEFAULT_TEMPS = [0.2, 0.5, 0.9, 1.3, 1.8]
DEFAULT_TOKENS = [1024, 2048, 4096]


# ------------ YAML Loader -------------
def _load_tools_from_catalog() -> list[dict[str, Any]]:
    if not os.path.exists(CATALOG_PATH):
        logger.warning(f"[VoxisPlanner] Tool catalog not found at {CATALOG_PATH}.")
        return []
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("endpoints", []) if isinstance(data, dict) else []
    except Exception as e:
        logger.error(f"[VoxisPlanner] Failed to parse catalog: {e}")
        return []


# ------------ Graph Ensurers -------------
async def _ensure_variant_grid() -> None:
    # Models
    for m in DEFAULT_MODELS:
        await cypher_query(
            """
            MERGE (m:Model {name: $m})
            WITH m
            MERGE (f:ArmFamily {family_id: "voxis.plan"})
            MERGE (f)-[:USES_MODEL]->(m)
            """,
            {"m": m},
        )

    # Temperatures
    for t in DEFAULT_TEMPS:
        await cypher_query(
            """
            MERGE (t:Temperature {value: $t})
            WITH t
            MERGE (f:ArmFamily {family_id: "voxis.plan"})
            MERGE (f)-[:USES_TEMPERATURE]->(t)
            """,
            {"t": t},
        )

    # Token limits
    for k in DEFAULT_TOKENS:
        await cypher_query(
            """
            MERGE (k:TokenLimit {value: $k})
            WITH k
            MERGE (f:ArmFamily {family_id: "voxis.plan"})
            MERGE (f)-[:USES_TOKENS]->(k)
            """,
            {"k": k},
        )


async def ensure_voxis_planner_family_schema() -> None:
    """
    Ensures the ArmFamily node, its variant grid (models/temps/tokens),
    and all strategy templates (baseline + YAML tool_focus_*) exist in Neo4j.
    """
    logger.info("[VoxisPlanner] Ensuring family schema (family + grid + strategies) in Neo4j...")

    # Family
    await cypher_query(
        """
        MERGE (f:ArmFamily {family_id: "voxis.plan"})
        ON CREATE SET f.mode = "voxis_planful", f.base_tags = ["planner", "voxis"]
        """,
    )

    # Grid
    await _ensure_variant_grid()

    # Baseline strategy
    await cypher_query(
        """
        MERGE (f:ArmFamily {family_id: "voxis.plan"})
        MERGE (f)-[:HAS_STRATEGY]->(s:StrategyTemplate {name: "no_tools"})
        ON CREATE SET s.tags = ["baseline"]
        """,
    )

    # Tool-focused strategies from YAML
    tools = _load_tools_from_catalog()
    for tool in tools:
        driver = tool.get("driver_name")
        endpoint = tool.get("endpoint")
        if not driver or not endpoint:
            continue
        strategy = f"tool_focus_{driver}.{endpoint}"
        tags = ["tool_focused"] + (tool.get("tags", []) or [])
        await cypher_query(
            """
            MERGE (f:ArmFamily {family_id: "voxis.plan"})
            MERGE (f)-[:HAS_STRATEGY]->(s:StrategyTemplate {name: $strategy})
            ON CREATE SET s.tags = $tags
            """,
            {"strategy": strategy, "tags": tags},
        )

    logger.info("[VoxisPlanner] Family schema ensured.")


# ------------ Graph Loaders for Bootstrap -------------
async def load_voxis_planner_strategies() -> list[ArmStrategyTemplate]:
    rows = (
        await cypher_query(
            """
        MATCH (f:ArmFamily {family_id: "voxis.plan"})-[:HAS_STRATEGY]->(s:StrategyTemplate)
        RETURN s.name AS name, s.tags AS tags
        ORDER BY s.name
        """,
        )
        or []
    )
    return [
        ArmStrategyTemplate(name=r["name"], tags=r.get("tags", [])) for r in rows if r.get("name")
    ]


# Provide an async strategy provider (bootstrapper will await this).
async def _strategy_templates_fn() -> list[ArmStrategyTemplate]:
    strategies = await load_voxis_planner_strategies()
    # Fallback to a baseline if the graph is somehow empty
    return strategies or [ArmStrategyTemplate(name="no_tools", tags=["baseline"])]


# ------------ Policy Graph Builder -------------
def build_voxis_policy_graph(arm_id: str, variant: ArmVariant) -> PolicyGraph:
    """
    Builds the PolicyGraph for a given variant.
    """
    effects = [
        LLMParamsEffect(
            model=variant.model,
            temperature=variant.temperature,
            max_tokens=variant.max_tokens,
        ),
        TagBiasEffect(tags=variant.tags),
    ]

    if variant.strategy.startswith("tool_focus_"):
        tool_name = variant.strategy.replace("tool_focus_", "")
        effects.append(ToolBiasEffect(weights={tool_name: 5.0}))
    elif variant.strategy == "no_tools":
        # discourage tool use slightly across all known tools
        all_tool_names = [
            f"{tool.get('driver_name')}.{tool.get('endpoint')}"
            for tool in _load_tools_from_catalog()
            if tool.get("driver_name") and tool.get("endpoint")
        ]
        if all_tool_names:
            effects.append(ToolBiasEffect(weights={name: 0.1 for name in all_tool_names}))

    return PolicyGraph(
        id=arm_id,
        version=2,
        nodes=[PolicyNode(id="prompt_main", type="prompt", model=variant.model)],
        effects=effects,
    )


# ------------ Relevance Filter -------------
def _relevance_filter(variant: ArmVariant) -> bool:
    # Slightly prune tiny contexts for tool-focused planners
    if variant.strategy.startswith("tool_focus_"):
        return variant.max_tokens >= 2048
    return True


# ------------ Export Family Config -------------
VOXIS_PLANNER_FAMILY = ArmFamilyConfig(
    family_id="voxis.plan",
    mode="voxis_planful",
    base_tags=["planner", "voxis"],
    strategy_templates_fn=_strategy_templates_fn,  # <-- ASYNC; bootstrapper awaits it
    policy_builder_fn=build_voxis_policy_graph,
    relevance_filter_fn=_relevance_filter,
)
