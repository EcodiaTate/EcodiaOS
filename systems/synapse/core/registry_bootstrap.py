# COMPLETE REPLACEMENT - GRAPH-DRIVEN VARIANTS, LEGACY-COMPATIBLE OUTPUT
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import inspect

# Added the missing 'itertools' import.
import itertools
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import List, Optional, Tuple, Union

# This guarantees that the @track_tool decorators have run and populated the
# global tool registry before any other module attempts to access it.
import systems.simula.nscs.agent_tools
from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.register_arm import register_arm
from systems.synapse.policy.policy_dsl import PolicyGraph

logger = logging.getLogger(__name__)

# Caching setup
BOOTSTRAP_CACHE = Path("/app/.cache/registry_bootstrap_fingerprint.txt")


def _fingerprint_data(obj: object) -> str:
    """Stable fingerprint for lists/dicts/classes."""
    try:
        blob = json.dumps(obj, sort_keys=True, default=str)
    except Exception:
        blob = str(obj)
    return hashlib.sha256(blob.encode()).hexdigest()


def _load_last_fingerprint() -> str | None:
    if not BOOTSTRAP_CACHE.exists():
        return None
    return BOOTSTRAP_CACHE.read_text().strip() or None


def _store_fingerprint(fp: str):
    BOOTSTRAP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_CACHE.write_text(fp)


# Back-compat global grid (used ONLY as fallback when graph lacks data)
MODELS = ["gpt-4o", "gpt-3.5-turbo", "gemini-1.5-pro-latest"]
TEMPERATURES = [0.2, 0.5, 0.9, 1.3, 1.8]
MAX_TOKENS = [1024, 2048, 4096]
BASE_MODEL_CONFIGS: list[tuple[str, float, int]] = list(
    itertools.product(MODELS, TEMPERATURES, MAX_TOKENS),
)


# Registry model classes
class ArmVariant:
    def __init__(
        self,
        strategy: str,
        model: str,
        temperature: float,
        max_tokens: int,
        tags: list[str] | None = None,
    ):
        self.strategy = strategy
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tags = tags or []


class ArmStrategyTemplate:
    def __init__(self, name: str, tags: list[str] | None = None):
        self.name = name
        self.tags = tags or []


class ArmFamilyConfig:
    def __init__(
        self,
        family_id: str,
        mode: str,
        base_tags: list[str],
        strategy_templates_fn: Callable[
            [], list[ArmStrategyTemplate] | Awaitable[list[ArmStrategyTemplate]],
        ]
        | None,
        policy_builder_fn: Callable[[str, ArmVariant], PolicyGraph] | None,
        relevance_filter_fn: Callable[[ArmVariant], bool] | None = None,
    ):
        self.family_id = family_id
        self.mode = mode
        self.base_tags = base_tags
        self.strategy_templates_fn = strategy_templates_fn
        self.policy_builder_fn = policy_builder_fn
        self.relevance_filter_fn = relevance_filter_fn or (lambda v: True)


def make_arm_id(family_id: str, variant: ArmVariant) -> str:
    model_short = "".join(filter(str.isalnum, variant.model.lower().replace("gpt-", "")))
    temp_short = f"t{int(variant.temperature * 10):02d}"
    tok_short = f"tok{variant.max_tokens // 1024}k"
    return f"{family_id}.{variant.strategy}.{model_short}.{temp_short}.{tok_short}.v2"


async def _resolve_strategy_templates(family: ArmFamilyConfig) -> list[ArmStrategyTemplate]:
    if not family.strategy_templates_fn:
        return []
    result = family.strategy_templates_fn()
    if inspect.isawaitable(result):
        return await result
    return result or []


def _run_coro_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


async def _load_graph_strategies(family_id: str) -> list[ArmStrategyTemplate]:
    rows = (
        await cypher_query(
            """
        MATCH (f:ArmFamily {family_id: $fid})-[:HAS_STRATEGY]->(s:StrategyTemplate)
        RETURN s.name AS name, s.tags AS tags
        ORDER BY s.name
        """,
            {"fid": family_id},
        )
        or []
    )
    return [
        ArmStrategyTemplate(name=r["name"], tags=r.get("tags", [])) for r in rows if r.get("name")
    ]


async def _load_graph_variant_grid(family_id: str) -> list[tuple[str, float, int]]:
    rows = (
        await cypher_query(
            """
        MATCH (f:ArmFamily {family_id: $fid})
        OPTIONAL MATCH (f)-[:USES_MODEL]->(m:Model)
        OPTIONAL MATCH (f)-[:USES_TEMPERATURE]->(t:Temperature)
        OPTIONAL MATCH (f)-[:USES_TOKENS]->(k:TokenLimit)
        WITH collect(DISTINCT m.name) AS models,
             collect(DISTINCT t.value) AS temps,
             collect(DISTINCT k.value) AS toks
        RETURN models, temps, toks
        """,
            {"fid": family_id},
        )
        or []
    )

    if not rows:
        return []

    models = [x for x in (rows[0].get("models") or []) if x]
    temps = [float(x) for x in (rows[0].get("temps") or []) if x is not None]
    toks = [int(x) for x in (rows[0].get("toks") or []) if x is not None]

    if not models:
        models = MODELS
        logger.warning(
            f"[{family_id}] No models found in graph, falling back to default grid.",
        )
    if not temps:
        temps = TEMPERATURES
        logger.warning(
            f"[{family_id}] No temperatures found in graph, falling back to default grid.",
        )
    if not toks:
        toks = MAX_TOKENS
        logger.warning(
            f"[{family_id}] No token limits found in graph, falling back to default grid.",
        )

    return [(str(m), float(t), int(k)) for (m, t, k) in itertools.product(models, temps, toks)]


async def _variants_from_graph_or_fallback(family: ArmFamilyConfig) -> list[ArmVariant]:
    strategies = await _load_graph_strategies(family.family_id)
    grid = await _load_graph_variant_grid(family.family_id)
    variants: list[ArmVariant] = []

    if strategies:
        for st in strategies:
            if st.name == "_singleton_":
                v = ArmVariant(family.family_id, "gpt-4o-mini", 0.7, 2048, tags=st.tags)
                variants.append(v)
            else:
                if not grid:
                    continue
                for model, temp, tokens in grid:
                    variants.append(
                        ArmVariant(st.name, model, float(temp), int(tokens), tags=st.tags),
                    )
        if variants:
            return variants
        logger.warning(
            f"[Bootstrap] Graph strategies found for '{family.family_id}' but grid was empty. Falling back to code-defined strategies.",
        )

    legacy_templates = await _resolve_strategy_templates(family)
    if not legacy_templates:
        logger.error(
            f"[{family.family_id}] CRITICAL: No strategy templates found from graph or code. Cannot generate arms.",
        )
        return []

    for st in legacy_templates:
        if st.name == "_singleton_":
            v = ArmVariant(family.family_id, "gpt-4o-mini", 0.7, 2048, tags=st.tags)
            variants.append(v)
        else:
            for model, temp, tokens in grid or BASE_MODEL_CONFIGS:
                variants.append(
                    ArmVariant(st.name, model, float(temp), int(tokens), tags=st.tags),
                )
    return variants


async def get_expected_arm_ids_for_family_async(family: ArmFamilyConfig) -> list[str]:
    variants = await _variants_from_graph_or_fallback(family)
    legacy_templates = await _resolve_strategy_templates(family)
    has_singleton = any(
        isinstance(t, ArmStrategyTemplate) and t.name == "_singleton_" for t in legacy_templates
    )
    ids: list[str] = []
    for v in variants:
        if v.strategy == family.family_id and has_singleton:
            ids.append(family.family_id)
        else:
            ids.append(make_arm_id(family.family_id, v))
    return ids


def get_expected_arm_ids_for_family(family: ArmFamilyConfig) -> list[str]:
    return _run_coro_sync(get_expected_arm_ids_for_family_async(family))


async def ensure_family_variants(family: ArmFamilyConfig) -> int:
    # Simula agent family is now handled entirely by its own bootstrap process.
    if family.family_id == "simula.agent.tools":
        return 0

    variants = await _variants_from_graph_or_fallback(family)
    variants = (
        [v for v in variants if family.relevance_filter_fn(v)]
        if family.relevance_filter_fn
        else variants
    )
    legacy_templates = await _resolve_strategy_templates(family)
    has_singleton = any(
        isinstance(t, ArmStrategyTemplate) and t.name == "_singleton_" for t in legacy_templates
    )
    tasks = []
    if not family.policy_builder_fn:
        return 0

    for v in variants:
        arm_id = (
            family.family_id
            if (v.strategy == family.family_id and has_singleton)
            else make_arm_id(family.family_id, v)
        )
        pg = family.policy_builder_fn(arm_id, v)
        tasks.append(register_arm(arm_id=arm_id, mode=family.mode, policy_graph=pg))

    if tasks:
        await asyncio.gather(*tasks)

    logger.info(f"[Bootstrap] Ensured {len(variants)} variants for arm family='{family.family_id}'")
    return len(variants)


async def prune_stale_arms(expected_ids: list[str]):
    logger.info("[Bootstrap] Checking for stale arms to prune...")
    try:
        result = (
            await cypher_query(
                "MATCH (p:PolicyArm) WHERE NOT p.id STARTS WITH 'dyn::' RETURN p.id AS id",
            )
            or []
        )
        existing_ids = {row["id"] for row in result}
        stale_ids = list(existing_ids - set(expected_ids))
        if not stale_ids:
            logger.info("[Bootstrap] No stale arms found.")
            return
        logger.warning(f"[Bootstrap] Found {len(stale_ids)} stale arms to prune. Deleting...")
        await cypher_query(
            "MATCH (p:PolicyArm) WHERE p.id IN $ids DETACH DELETE p",
            {"ids": stale_ids},
        )
    except Exception as e:
        logger.error(f"[Bootstrap] Error during pruning: {e}")


async def _ensure_schema():
    logger.info("[Bootstrap] Ensuring database schema constraints exist...")

    # We do NOT drop constraints here anymore (dropping + concurrent writes = races).
    constraints = [
        "CREATE CONSTRAINT policy_arm_pk IF NOT EXISTS FOR (p:PolicyArm) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT model_pk IF NOT EXISTS FOR (m:Model) REQUIRE m.name IS UNIQUE",
        "CREATE CONSTRAINT temp_pk IF NOT EXISTS FOR (t:Temperature) REQUIRE t.value IS UNIQUE",
        "CREATE CONSTRAINT token_pk IF NOT EXISTS FOR (k:TokenLimit) REQUIRE k.value IS UNIQUE",
        "CREATE CONSTRAINT family_pk IF NOT EXISTS FOR (f:ArmFamily) REQUIRE f.family_id IS UNIQUE",
        "CREATE CONSTRAINT strategy_pk IF NOT EXISTS FOR (s:StrategyTemplate) REQUIRE s.name IS UNIQUE",
    ]
    for q in constraints:
        try:
            await cypher_query(q)
        except Exception as e:
            logger.error(f"[Bootstrap] Could not ensure constraint: {q} -> {e}")


async def _ensure_singleton_strategy_serial() -> None:
    """
    Serialize creation of the shared `_singleton_` StrategyTemplate node.
    MUST run before any concurrent family bootstraps.
    """
    try:
        # With the uniqueness constraint in place, this MERGE is safe and idempotent.
        await cypher_query("MERGE (s:StrategyTemplate {name: '_singleton_'}) RETURN s")
        logger.info("[Bootstrap] Ensured shared StrategyTemplate '_singleton_'")
    except Exception as e:
        # If anything goes wrong here, abort early rather than letting parallel tasks race.
        logger.error("[Bootstrap] CRITICAL: Failed to ensure '_singleton_' StrategyTemplate: %r", e)
        raise


async def ensure_minimum_arms():
    """
    Main startup sequence to ensure all necessary schema and policy arms exist.
    """
    logger.info("[Bootstrap] Beginning startup: ensuring schema and all policy arms...")

    from systems.synapse.policy.families.base import BASE_FAMILY, ensure_base_family_schema
    from systems.synapse.policy.families.simula_agent import ensure_simula_agent_families
    from systems.synapse.policy.families.voxis_planner import (
        VOXIS_PLANNER_FAMILY,
        ensure_voxis_planner_family_schema,
    )
    from systems.synapse.policy.families.voxis_synthesizer import (
        VOXIS_SYNTHESIZER_FAMILY,
        ensure_voxis_synthesizer_family_schema,
    )

    try:
        from systems.synapse.policy.families.unity_arms import (
            ALL_UNITY_FAMILIES,
            ensure_unity_families_schema,
        )
    except ImportError:
        logger.warning("[Bootstrap] Unity arm families not found, skipping.")

        async def ensure_unity_families_schema():
            return None

        ALL_UNITY_FAMILIES = []

    # 1) Constraints first (serial).
    await _ensure_schema()

    # 2) Ensure the shared `_singleton_` node ONCE (serial).
    await _ensure_singleton_strategy_serial()

    # 3) Now it’s safe to run family bootstraps in parallel.
    await asyncio.gather(
        ensure_base_family_schema(),
        ensure_voxis_planner_family_schema(),
        ensure_voxis_synthesizer_family_schema(),
        ensure_simula_agent_families(),      # ← use the new MDO-ARCH bootstrapping
        ensure_unity_families_schema(),
    )

    all_families = [
        BASE_FAMILY,
        VOXIS_PLANNER_FAMILY,
        VOXIS_SYNTHESIZER_FAMILY,
    ] + ALL_UNITY_FAMILIES

    logger.info("[Bootstrap] Forcing full bootstrap to ensure database consistency...")

    all_expected_ids: list[str] = []
    from systems.simula.nscs.agent_tools import get_all_tool_arm_ids

    all_expected_ids.extend(get_all_tool_arm_ids())

    for family in all_families:
        ids = await get_expected_arm_ids_for_family_async(family)
        all_expected_ids.extend(ids)

    await prune_stale_arms(all_expected_ids)

    total_created = 0
    for family in all_families:
        total_created += await ensure_family_variants(family)

    logger.info(f"[Bootstrap] Completed policy arm generation. Total ensured: {total_created}.")
