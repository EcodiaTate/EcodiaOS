# systems/synapse/policy/families/simula_agent.py
# MDO-ARCH: This is now the "Tool Service Family" bootstrapping module.
# Its purpose is to perform a one-time, intelligent registration of all Simula tools
# into the Neo4j graph, complete with semantic vector embeddings.

from __future__ import annotations

import inspect
import json
import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any, Dict, List

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query
from systems.simula.code_sim.telemetry import get_tracked_tools
from systems.synapse.core.registry_bootstrap import (
    ArmFamilyConfig,
    ArmStrategyTemplate,
    ArmVariant,
    ensure_family_variants,
)
from systems.synapse.policy.policy_dsl import PolicyGraph

log = logging.getLogger(__name__)

FAMILY_ID = "simula.agent.tools"

# ==============================
# 1. Self-Documenting Schema & Document Generator
# ==============================


def _generate_json_schema_for_tool(func: Callable[..., Any]) -> dict[str, Any]:
    """
    Introspects a function's signature and docstring to build a rich
    JSON schema for its parameters, making the tool self-documenting.
    """
    sig = inspect.signature(func)
    docstring = inspect.getdoc(func) or ""

    doc_params = {}
    args_section_match = re.search(r"Args:\n(.*?)(Returns:|Raises:|\Z)", docstring, re.DOTALL)
    if args_section_match:
        param_regex = re.compile(r"^\s*(\w+)\s*:\s*(.*)", re.MULTILINE)
        for match in param_regex.finditer(args_section_match.group(1)):
            doc_params[match.group(1)] = match.group(2).strip()

    schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    for name, param in sig.parameters.items():
        if name in ("self", "cls", "kwargs", "args"):
            continue

        prop: dict[str, Any] = {}
        type_name = str(param.annotation).lower()

        if "str" in type_name:
            prop["type"] = "string"
        elif "int" in type_name:
            prop["type"] = "integer"
        elif "float" in type_name:
            prop["type"] = "number"
        elif "bool" in type_name:
            prop["type"] = "boolean"
        elif any(k in type_name for k in ["list", "dict", "any"]):
            prop["type"] = "object"
            prop["description"] = f"A JSON object representing a Python '{type_name}'."
        else:
            prop["type"] = "string"

        if name in doc_params:
            prop["description"] = doc_params[name]

        if param.default is inspect.Parameter.empty:
            schema["required"].append(name)
        else:
            prop["default"] = param.default

        schema["properties"][name] = prop

    return schema


def _create_embedding_document(tool_name: str, meta: dict[str, Any]) -> str:
    """
    Creates a rich text document for a tool to be used for generating a vector embedding.
    This document captures the full semantics of the tool's purpose and usage.
    """
    func = meta.get("func")
    if not func:
        return ""

    description = inspect.getdoc(func) or f"Simula tool: {tool_name}"
    schema = _generate_json_schema_for_tool(func)

    param_descriptions = []
    for name, prop in schema.get("properties", {}).items():
        param_desc = (
            f"- {name} ({prop.get('type', 'any')}): {prop.get('description', 'No description.')}"
        )
        param_descriptions.append(param_desc)

    param_section = "\n".join(param_descriptions)

    return f"""
Tool Name: {tool_name}
Purpose: {description}
Parameters:
{param_section}
Modes: {', '.join(meta.get("modes", []))}
"""


# ==============================
# 2. Graph Bootstrap Logic (The Core of the New Approach)
# ==============================


async def bootstrap_simula_tools_in_graph() -> None:
    """
    Discovers all Simula tools, generates semantic embeddings for them,
    and upserts them into the Neo4j graph as `PolicyArm` nodes.
    This is the definitive, one-time setup process for making tools discoverable.
    """
    log.info(f"[{FAMILY_ID}] Starting semantic bootstrapping of all Simula tools...")

    tools_with_meta = get_tracked_tools()
    if not tools_with_meta:
        log.warning(f"[{FAMILY_ID}] No tools found via `get_tracked_tools()`. Aborting bootstrap.")
        return

    log.info(f"[{FAMILY_ID}] Found {len(tools_with_meta)} tools to process.")

    # Create embedding tasks to run in parallel
    embedding_tasks: dict[str, Coroutine] = {}
    for tool_name, meta in tools_with_meta.items():
        doc = _create_embedding_document(tool_name, meta)
        if doc:
            embedding_tasks[tool_name] = get_embedding(doc, task_type="RETRIEVAL_DOCUMENT")

    # Await all embeddings
    import asyncio

    embeddings = await asyncio.gather(*embedding_tasks.values())
    tool_embeddings = dict(zip(embedding_tasks.keys(), embeddings))

    # Prepare data for a single, efficient Cypher query
    arms_to_create = []
    for tool_name, meta in tools_with_meta.items():
        if tool_name not in tool_embeddings:
            continue

        func = meta.get("func")
        if not func:
            continue

        tool_modes = meta.get("modes", ["general"])
        mode_tags = [f"mode::{m}" for m in tool_modes]
        tags = ["simula", "tool-api", tool_name] + mode_tags

        parameters_schema = _generate_json_schema_for_tool(func)
        description = inspect.getdoc(func) or f"Directly executes the Simula tool: {tool_name}"
        arm_id = f"simula.agent.tools.{tool_name}"

        # This metadata structure is critical. It's what `lenses.py` will query.
        policy_graph_meta = {
            "tool_name": tool_name,
            "tool_modes": tool_modes,
            "parameters_schema": parameters_schema,
        }

        arms_to_create.append(
            {
                "id": arm_id,
                "family_id": FAMILY_ID,
                "description": description,
                "tags": tags,
                "policy_graph_meta_str": json.dumps(policy_graph_meta),
                "embedding": tool_embeddings[tool_name],
                "mode": "simula_tool_api",  # Static mode for this family
            }
        )

    # Upsert all arms into Neo4j in one go
    if arms_to_create:
        upsert_query = """
        UNWIND $arms AS arm_data
        MERGE (a:PolicyArm {id: arm_data.id})
        SET a.family_id = arm_data.family_id,
            a.description = arm_data.description,
            a.tags = arm_data.tags,
            a.policy_graph_meta = arm_data.policy_graph_meta_str,
            a.embedding = arm_data.embedding,
            a.mode = arm_data.mode,
            a.created_ts = timestamp()
        """
        await cypher_query(upsert_query, {"arms": arms_to_create})
        log.info(
            f"[{FAMILY_ID}] Successfully upserted {len(arms_to_create)} semantically-indexed tools into the graph."
        )
    else:
        log.warning(f"[{FAMILY_ID}] No valid tools with embeddings were generated to upsert.")

    # AFTER bootstrapping, you must create the vector index.
    # This is a one-time operation per database.
    index_query = """
    CREATE VECTOR INDEX policyArmIndex IF NOT EXISTS
    FOR (p:PolicyArm) ON (p.embedding)
    OPTIONS { indexConfig: {
        `vector.dimensions`: 3072, // IMPORTANT: Match your embedding model's dimensions
        `vector.similarity_function`: 'cosine'
    }}
    """
    try:
        # Note: This might require specific DB permissions.
        await cypher_query(index_query)
        log.info(f"[{FAMILY_ID}] Successfully created or verified 'policyArmIndex' vector index.")
    except Exception as e:
        log.error(
            f"[{FAMILY_ID}] FAILED to create vector index 'policyArmIndex'. "
            f"This is a critical error. Manual intervention may be required. Error: {e}"
        )


# ==============================
# 3. Arm Family Definition (Simplified)
# ==============================
# This section is now less critical for runtime, as the bootstrapping process
# handles the heavy lifting. It remains for conceptual organization.


def get_simula_tool_strategies() -> list[ArmStrategyTemplate]:
    """
    Dynamically discovers all registered Simula tools to provide a list of strategies.
    This is used for conceptual grouping and potential UI displays, not for direct execution.
    """
    tools_with_meta = get_tracked_tools()
    return [
        ArmStrategyTemplate(
            name=tool_name,
            tags=["simula", "tool", "single-step"] + [f"mode::{m}" for m in meta.get("modes", [])],
        )
        for tool_name, meta in sorted(tools_with_meta.items())
    ]


SIMULA_AGENT_TOOL_FAMILY = ArmFamilyConfig(
    family_id=FAMILY_ID,
    mode="simula_tool_api",
    base_tags=["simula", "tool-api"],
    strategy_templates_fn=get_simula_tool_strategies,
    # The policy builder is no longer needed at runtime, as policies are pre-built and stored.
    policy_builder_fn=None,
)

# ==============================
# 4. Public API for Bootstrapping
# ==============================


async def ensure_simula_agent_family_schema() -> None:
    """
    Public-facing function to run the entire bootstrapping process for Simula tools.
    This should be called once during application setup or deployment.
    """
    await bootstrap_simula_tools_in_graph()
