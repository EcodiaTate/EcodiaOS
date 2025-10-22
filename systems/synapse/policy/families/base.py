# systems/synapse/policy/families/base.py
from __future__ import annotations

import asyncio
import logging
from typing import List

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.register_arm import register_arm
from systems.synapse.core.registry_bootstrap import (
    ArmFamilyConfig,
    ArmStrategyTemplate,
    ArmVariant,
    make_arm_id,
)
from systems.synapse.policy.policy_dsl import LLMParamsEffect, PolicyGraph, PolicyNode

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Grid defaults (kept small but representative)
# -------------------------------------------------------------------
DEFAULT_MODELS = ["gpt-4o", "gpt-3.5-turbo", "gemini-2.0-pro"]
DEFAULT_TEMPS = [0.1, 0.4, 0.7, 1.1, 1.5]
DEFAULT_TOKENS = [1024, 2048, 4096]

# Synapse sometimes refers to "short" model selectors.
MODEL_ALIASES = {
    "35turbo": "gpt-3.5-turbo",
    "4o": "gpt-4o",
    "4omini": "gpt-4o-mini",
    "gemini-2.0-pro": "gemini-2.0-pro",
}


def _resolve_model_name(m: str) -> str:
    return MODEL_ALIASES.get(m, m)


def _policy_graph_for(model: str, temperature: float, max_tokens: int) -> PolicyGraph:
    """Minimal params-only policy graph suitable for generic use."""
    return PolicyGraph(
        id="",  # filled at registration
        version=1,
        nodes=[PolicyNode(id="prompt", type="prompt", model=model)],
        effects=[
            LLMParamsEffect(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        ],
    )


async def _register_base_variant(model: str, temperature: float, tokens: int):
    """Register one base.params.* arm (mode='generic')."""
    v = ArmVariant(
        strategy="params",
        model=_resolve_model_name(model),
        temperature=float(temperature),
        max_tokens=int(tokens),
        tags=[],
    )
    arm_id = make_arm_id("base", v)  # base.params.<modelShort>.<tXX>.<tokNk>.v2
    pg = _policy_graph_for(v.model, v.temperature, v.max_tokens)
    pg.id = arm_id
    await register_arm(arm_id=arm_id, mode="generic", policy_graph=pg)


async def ensure_base_family_schema() -> None:
    """
    Graph-side seed + concrete registration of full base.* grid (mode='generic').
    """
    # Family (mode set to 'generic' because these are generic arms)
    await cypher_query(
        """
        MERGE (f:ArmFamily {family_id: "base"})
        ON CREATE SET f.mode = "generic", f.base_tags = ["general", "generic", "base"]
        """,
    )

    # Grid nodes (models/temps/tokens) so graph remains the source of truth
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

    # Strategy: single 'params' template (matches legacy selector)
    await cypher_query(
        """
        MERGE (f:ArmFamily {family_id: "base"})
        MERGE (f)-[:HAS_STRATEGY]->(s:StrategyTemplate {name: "params"})
        """,
    )

    # Build product grid from graph if present; else fallback to defaults
    rows = (
        await cypher_query(
            """
        MATCH (f:ArmFamily {family_id: "base"})
        OPTIONAL MATCH (f)-[:USES_MODEL]->(m:Model)
        OPTIONAL MATCH (f)-[:USES_TEMPERATURE]->(t:Temperature)
        OPTIONAL MATCH (f)-[:USES_TOKENS]->(k:TokenLimit)
        WITH collect(DISTINCT m.name) AS models,
             collect(DISTINCT t.value) AS temps,
             collect(DISTINCT k.value) AS toks
        RETURN models, temps, toks
        """,
        )
        or []
    )

    models = (rows and rows[0].get("models")) or DEFAULT_MODELS
    temps = (rows and rows[0].get("temps")) or DEFAULT_TEMPS
    toks = (rows and rows[0].get("toks")) or DEFAULT_TOKENS

    # Register the full base.params grid (mode='generic')
    tasks = []
    for m in models:
        for t in temps:
            for k in toks:
                tasks.append(_register_base_variant(str(m), float(t), int(k)))

    # Ensure explicit legacy selector observed in logs:
    # base.params.35turbo.t01.tok1k.v2
    tasks.append(_register_base_variant("35turbo", 0.1, 1024))

    await asyncio.gather(*tasks)
    logger.info("[BaseFamily] Registered full base.params grid (mode='generic').")


# -------------------- Graph-driven templating for bootstrapper --------------------


async def _load_base_strategies() -> list[ArmStrategyTemplate]:
    rows = (
        await cypher_query(
            """
        MATCH (f:ArmFamily {family_id: "base"})-[:HAS_STRATEGY]->(s:StrategyTemplate)
        RETURN s.name AS name, s.tags AS tags
        """,
        )
        or []
    )
    return [
        ArmStrategyTemplate(name=r["name"], tags=r.get("tags", [])) for r in rows if r.get("name")
    ]


async def _strategy_templates_fn() -> list[ArmStrategyTemplate]:
    """
    Async entrypoint used by the registry. Falls back to a single 'params' template.
    """
    strategies = await _load_base_strategies()
    return strategies or [ArmStrategyTemplate(name="params")]


def _build_params_only_graph(arm_id: str, variant: ArmVariant) -> PolicyGraph:
    # This is used by the generic registry path; we still set mode='generic' at registration time.
    return PolicyGraph(
        id=arm_id,
        version=1,
        nodes=[PolicyNode(id="prompt", type="prompt", model=variant.model)],
        effects=[
            LLMParamsEffect(
                model=variant.model,
                temperature=variant.temperature,
                max_tokens=variant.max_tokens,
            ),
        ],
    )


# Exported family config; the core bootstrapper will use this too.
BASE_FAMILY = ArmFamilyConfig(
    family_id="base",
    mode="generic",  # important: base.* arms live in the 'generic' mode
    base_tags=["general", "generic", "base"],
    strategy_templates_fn=_strategy_templates_fn,
    policy_builder_fn=_build_params_only_graph,
)
