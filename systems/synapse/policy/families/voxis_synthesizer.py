# COMPLETE REPLACEMENT - GRAPH-AWARE AND EXPANDED STRATEGIES

from __future__ import annotations

import logging
from typing import List

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.registry_bootstrap import ArmFamilyConfig, ArmStrategyTemplate, ArmVariant
from systems.synapse.policy.policy_dsl import (
    LLMParamsEffect,
    PolicyGraph,
    PolicyNode,
    StyleInjectionEffect,
    TagBiasEffect,
)

logger = logging.getLogger(__name__)

# -------- Default grid for this family (ensured into graph) --------
DEFAULT_MODELS = ["gpt-4o", "gpt-3.5-turbo", "gemini-2.0-pro"]
DEFAULT_TEMPS = [0.2, 0.5, 0.9, 1.3, 1.8]
DEFAULT_TOKENS = [512, 2048, 4096]


# ----------------- Graph Ensurers (family + grid + strategies) -----------------
async def _ensure_variant_grid() -> None:
    # Models
    for m in DEFAULT_MODELS:
        await cypher_query(
            """
            MERGE (m:Model {name: $m})
            WITH m
            MERGE (f:ArmFamily {family_id: "voxis.synthesis"})
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
            MERGE (f:ArmFamily {family_id: "voxis.synthesis"})
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
            MERGE (f:ArmFamily {family_id: "voxis.synthesis"})
            MERGE (f)-[:USES_TOKENS]->(k)
            """,
            {"k": k},
        )


async def ensure_voxis_synthesizer_family_schema() -> None:
    """Ensures the Synthesizer family, its variant grid, and all stylistic strategies exist in Neo4j."""
    logger.info(
        "[VoxisSynthesizer] Ensuring family schema (family + grid + strategies) in Neo4j..."
    )

    # Family
    await cypher_query(
        """
        MERGE (f:ArmFamily {family_id: "voxis.synthesis"})
        ON CREATE SET f.mode = "synthesis", f.base_tags = ["synthesizer", "voxis"]
        """,
    )

    # Grid
    await _ensure_variant_grid()

    # Stylistic strategies
    strategies = [
        ("concise", ["style_concise", "brief"]),
        ("detailed", ["style_detailed", "thorough"]),
        ("empathetic", ["style_empathetic", "warm"]),
        ("professional", ["style_professional", "formal"]),
        ("academic", ["style_academic", "technical"]),
        ("storyteller", ["style_narrative", "engaging"]),
        ("socratic", ["style_socratic", "guiding"]),
        ("bulleted_list", ["style_structured", "list"]),
        ("step_by_step", ["style_instructional", "how_to"]),
        ("simple_language", ["style_simple", "accessible"]),
        ("prescriptive", ["style_actionable", "direct"]),
        ("suggestive", ["style_options", "collaborative"]),
    ]

    for name, tags in strategies:
        await cypher_query(
            """
            MERGE (f:ArmFamily {family_id: "voxis.synthesis"})
            MERGE (f)-[:HAS_STRATEGY]->(s:StrategyTemplate {name: $name})
            ON CREATE SET s.tags = $tags
            """,
            {"name": name, "tags": tags},
        )

    logger.info("[VoxisSynthesizer] Family schema ensured.")


# ----------------- Load Strategy Templates from Graph -----------------
async def load_voxis_synthesizer_strategies() -> list[ArmStrategyTemplate]:
    rows = (
        await cypher_query(
            """
        MATCH (f:ArmFamily {family_id: "voxis.synthesis"})-[:HAS_STRATEGY]->(s:StrategyTemplate)
        RETURN s.name AS name, s.tags AS tags
        ORDER BY s.name
        """,
        )
        or []
    )
    return [
        ArmStrategyTemplate(name=row["name"], tags=row.get("tags", []))
        for row in rows
        if row.get("name")
    ]


# Provide an async strategy provider (bootstrapper will await this).
async def _strategy_templates_fn() -> list[ArmStrategyTemplate]:
    strategies = await load_voxis_synthesizer_strategies()
    # Fallback: keep at least one style available
    return strategies or [ArmStrategyTemplate(name="concise", tags=["style_concise", "brief"])]


# ----------------- Policy Graph Builder -----------------
def build_synthesizer_policy_graph(arm_id: str, variant: ArmVariant) -> PolicyGraph:
    """
    Creates a PolicyGraph for the synthesizer with effects that guide its style,
    mapping the strategy name to a specific style dictionary.
    """
    effects = [
        LLMParamsEffect(
            model=variant.model, temperature=variant.temperature, max_tokens=variant.max_tokens
        ),
        TagBiasEffect(tags=variant.tags),
    ]

    style_dict = {}
    strategy = variant.strategy

    # --- Verbosity ---
    if strategy == "concise":
        style_dict = {"verbosity": "brief", "tone": "direct and to-the-point"}
    elif strategy == "detailed":
        style_dict = {
            "verbosity": "thorough",
            "tone": "informative",
            "constraints": ["provide step-by-step reasoning", "explain underlying concepts"],
        }

    # --- Tone / Persona ---
    elif strategy == "empathetic":
        style_dict = {"verbosity": "normal", "tone": "warm, supportive, and empathetic"}
    elif strategy == "professional":
        style_dict = {"verbosity": "normal", "tone": "formal and professional"}
    elif strategy == "academic":
        style_dict = {
            "verbosity": "thorough",
            "tone": "academic and precise",
            "constraints": ["cite sources where possible", "define key terms"],
        }
    elif strategy == "storyteller":
        style_dict = {
            "verbosity": "detailed",
            "tone": "narrative and engaging",
            "constraints": ["use analogies and examples"],
        }
    elif strategy == "socratic":
        style_dict = {
            "verbosity": "normal",
            "tone": "inquisitive and guiding",
            "constraints": [
                "ask clarifying questions to guide the user",
                "encourage critical thinking",
            ],
        }

    # --- Structure ---
    elif strategy == "bulleted_list":
        style_dict = {
            "verbosity": "normal",
            "tone": "clear and organized",
            "constraints": ["format main points as a bulleted list"],
        }
    elif strategy == "step_by_step":
        style_dict = {
            "verbosity": "detailed",
            "tone": "instructional",
            "constraints": ["format the response as a numbered list of sequential steps"],
        }

    # --- Complexity ---
    elif strategy == "simple_language":
        style_dict = {
            "verbosity": "brief",
            "tone": "simple and accessible",
            "constraints": [
                "use simple, everyday language",
                "avoid jargon and complex sentences",
                "explain like I'm 10",
            ],
        }

    # --- Actionability ---
    elif strategy == "prescriptive":
        style_dict = {
            "verbosity": "normal",
            "tone": "authoritative and clear",
            "constraints": [
                "provide a direct recommendation or instruction",
                "state the next action clearly",
            ],
        }
    elif strategy == "suggestive":
        style_dict = {
            "verbosity": "normal",
            "tone": "helpful and collaborative",
            "constraints": [
                "offer a few different options or suggestions",
                "present pros and cons if applicable",
            ],
        }

    if style_dict:
        effects.append(StyleInjectionEffect(style_dict=style_dict))

    return PolicyGraph(
        id=arm_id,
        version=2,
        nodes=[PolicyNode(id="synthesis_prompt", type="prompt", model=variant.model)],
        effects=effects,
    )


# ----------------- Relevance Filter -----------------
def _relevance_filter(variant: ArmVariant) -> bool:
    """Filters the grid for synthesizer arms."""
    return variant.temperature < 1.8


# ----------------- Export Family Config -----------------
VOXIS_SYNTHESIZER_FAMILY = ArmFamilyConfig(
    family_id="voxis.synthesis",
    mode="synthesis",
    base_tags=["synthesizer", "voxis"],
    strategy_templates_fn=_strategy_templates_fn,  # <-- ASYNC, will be awaited by bootstrapper
    relevance_filter_fn=_relevance_filter,
    policy_builder_fn=build_synthesizer_policy_graph,
)
