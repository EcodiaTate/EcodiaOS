# NEW FILE - GRAPH-COMPATIBLE UNITY ARM FAMILIES

from __future__ import annotations

from typing import List

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry_bootstrap import ArmFamilyConfig, ArmStrategyTemplate, ArmVariant
from systems.synapse.policy.policy_dsl import (
    LLMParamsEffect,
    PolicyGraph,
    PolicyNode,
    TagBiasEffect,
)


# --- Shared Policy Builder for Simple Arms ---
def build_simple_policy_graph(arm_id: str, variant: ArmVariant) -> PolicyGraph:
    """A generic builder for simple arms that only need basic LLM params."""
    return PolicyGraph(
        id=arm_id,
        version=2,
        nodes=[PolicyNode(id="prompt_main", type="prompt", model=variant.model)],
        effects=[
            LLMParamsEffect(
                model=variant.model,
                temperature=variant.temperature,
                max_tokens=variant.max_tokens,
            ),
            TagBiasEffect(tags=variant.tags),
        ],
    )


# --- Unity Arm Definitions ---
UNITY_DEFINITIONS = [
    {"id": "unity_escalate", "mode": "unity", "tags": ["unity", "escalate"]},
    {"id": "unity_reflect", "mode": "unity", "tags": ["unity", "reflect"]},
    {"id": "unity_resolve", "mode": "unity", "tags": ["unity", "resolve"]},
    {"id": "unity_risk_review", "mode": "unity", "tags": ["unity", "risk_review"]},
]

# Conversational utility singleton (kept as-is)
CONVERSATIONAL_DEFINITION = {
    "id": "conversational_response",
    "mode": "tool",
    "tags": ["conversational"],
}

# --- Minimal default grid (optional, forward-compatible) ---
DEFAULT_MODELS = ["gpt-4o"]  # single model is fine for utility arms
DEFAULT_TEMPS = [0.7]  # steady temperature
DEFAULT_TOKENS = [2048]  # safe default


async def _ensure_family_schema(family_id: str, mode: str, base_tags: list[str]) -> None:
    # Family
    await cypher_query(
        """
        MERGE (f:ArmFamily {family_id: $fid})
        ON CREATE SET f.mode = $mode, f.base_tags = $tags
        """,
        {"fid": family_id, "mode": mode, "tags": base_tags},
    )

    # Singleton strategy marker for compatibility with the bootstrapper
    await cypher_query(
        """
        MERGE (f:ArmFamily {family_id: $fid})
WITH f
MATCH (s:StrategyTemplate {name: "_singleton_"})
MERGE (f)-[:HAS_STRATEGY]->(s)

        """,
        {"fid": family_id},
    )

    # Optional grid for future (not required for singletons)
    for m in DEFAULT_MODELS:
        await cypher_query(
            """
            MERGE (m:Model {name: $m})
            WITH m
            MERGE (f:ArmFamily {family_id: $fid})
            MERGE (f)-[:USES_MODEL]->(m)
            """,
            {"fid": family_id, "m": m},
        )

    for t in DEFAULT_TEMPS:
        await cypher_query(
            """
            MERGE (t:Temperature {value: $t})
            WITH t
            MERGE (f:ArmFamily {family_id: $fid})
            MERGE (f)-[:USES_TEMPERATURE]->(t)
            """,
            {"fid": family_id, "t": t},
        )

    for k in DEFAULT_TOKENS:
        await cypher_query(
            """
            MERGE (k:TokenLimit {value: $k})
            WITH k
            MERGE (f:ArmFamily {family_id: $fid})
            MERGE (f)-[:USES_TOKENS]->(k)
            """,
            {"fid": family_id, "k": k},
        )


# --- Public: ensure all Unity family schemas exist (called by bootstrapper) ---
async def ensure_unity_families_schema() -> None:
    # Unity singletons
    for defn in UNITY_DEFINITIONS:
        await _ensure_family_schema(defn["id"], defn["mode"], defn["tags"])
    # Conversational singleton
    await _ensure_family_schema(
        CONVERSATIONAL_DEFINITION["id"],
        CONVERSATIONAL_DEFINITION["mode"],
        CONVERSATIONAL_DEFINITION["tags"],
    )


# --- Strategy templates fn for singletons (bootstrapper uses this to preserve singleton ID behavior) ---
def _singleton() -> list[ArmStrategyTemplate]:
    return [ArmStrategyTemplate(name="_singleton_")]


# --- Family configs (registered by the core bootstrapper) ---
ALL_UNITY_FAMILIES: list[ArmFamilyConfig] = [
    ArmFamilyConfig(
        family_id=defn["id"],
        mode=defn["mode"],
        base_tags=defn["tags"],
        strategy_templates_fn=_singleton,  # sync is OK; resolver supports sync/async
        relevance_filter_fn=lambda v: True,
        policy_builder_fn=build_simple_policy_graph,
    )
    for defn in UNITY_DEFINITIONS
]

# Conversational family (added last)
CONVERSATIONAL_FAMILY = ArmFamilyConfig(
    family_id=CONVERSATIONAL_DEFINITION["id"],
    mode=CONVERSATIONAL_DEFINITION["mode"],
    base_tags=CONVERSATIONAL_DEFINITION["tags"],
    strategy_templates_fn=_singleton,
    relevance_filter_fn=lambda v: True,
    policy_builder_fn=build_simple_policy_graph,
)

ALL_UNITY_FAMILIES.append(CONVERSATIONAL_FAMILY)
