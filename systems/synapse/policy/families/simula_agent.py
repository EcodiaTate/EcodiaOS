# MDO-ARCH: This is the Simula Agent & Tool Bootstrapping Service.
# Its purpose is to perform a one-time, intelligent registration of ALL Simula
# agents and tools into the Neo4j graph, complete with semantic vector embeddings.

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query
from systems.simula.code_sim.telemetry import get_tracked_tools

log = logging.getLogger(__name__)

# ==============================================================================
# 1. Agent & Tool Family Definitions
# ==============================================================================

# Declarative definitions for all cognitive agents used in deliberation.
# This is the "source of truth" for what these agents are and how they should behave.
DELIBERATION_AGENTS = [
    {
        "arm_id": "simula.deliberation.planner.hypothesis_generator",
        "family_id": "simula.agent.deliberation.planners",
        "description": "A creative strategist that generates multiple, distinct, and competing initial plans (hypotheses) to achieve a goal. It explores diverse strategies, such as cautious vs. direct approaches, using only the available tools.",
        "tags": ["simula", "deliberation", "planner", "hypothesis-generator"],
        "policy_graph_meta": {
            "effects": [{"type": "LLMParamsEffect", "model": "gpt-4o", "temperature": 0.6}],
        },
    },
    {
        "arm_id": "simula.deliberation.planner.synthesizer",
        "family_id": "simula.agent.deliberation.planners",
        "description": "A logical synthesizer that creates a new, superior plan by combining the strengths of multiple parent plans and explicitly addressing their audited flaws. It focuses on creating a coherent, novel strategy.",
        "tags": ["simula", "deliberation", "planner", "synthesizer"],
        "policy_graph_meta": {
            "effects": [{"type": "LLMParamsEffect", "model": "gpt-4o", "temperature": 0.4}],
        },
    },
    {
        "arm_id": "simula.deliberation.coordinator.moderator",
        "family_id": "simula.agent.deliberation.coordinators",
        "description": "A pragmatic, resource-aware moderator that directs the deliberation process. It assesses the state of all competing plans and their audit reports to make strategic decisions: approve, synthesize, continue, or terminate.",
        "tags": ["simula", "deliberation", "coordinator", "moderator"],
        "policy_graph_meta": {
            "effects": [{"type": "LLMParamsEffect", "model": "gpt-4o-mini", "temperature": 0.2}],
        },
    },
    {
        "arm_id": "simula.deliberation.auditor.generic",
        "family_id": "simula.agent.deliberation.auditors",
        "description": "A generic, focused specialist auditor. It evaluates a plan strictly against a single, narrow criterion provided in its prompt summary, such as security, import correctness, or goal obedience. It provides a concise, decisive verdict.",
        "tags": ["simula", "deliberation", "auditor", "generic"],
        "policy_graph_meta": {
            "effects": [{"type": "LLMParamsEffect", "model": "gpt-4o-mini", "temperature": 0.1}],
        },
    },
]

# ==============================================================================
# 2. Self-Documenting Schema & Embedding Document Generation
# ==============================================================================


def _generate_json_schema_for_tool(func: Callable[..., Any]) -> dict[str, Any]:
    """Introspects a function's signature and docstring to build a rich JSON schema."""
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


def _create_embedding_document_for_tool(tool_name: str, meta: dict[str, Any]) -> str:
    """Creates a rich text document for a tool to generate a vector embedding."""
    func = meta.get("func")
    if not func:
        return ""
    description = inspect.getdoc(func) or f"Simula tool: {tool_name}"
    schema = _generate_json_schema_for_tool(func)
    param_descriptions = [
        f"- {name} ({prop.get('type', 'any')}): {prop.get('description', 'No description.')}"
        for name, prop in schema.get("properties", {}).items()
    ]
    return (
        f"Tool Name: {tool_name}\nPurpose: {description}\nParameters:\n"
        + "\n".join(param_descriptions)
        + f"\nModes: {', '.join(meta.get('modes', []))}"
    )


# ==============================================================================
# 3. Graph Bootstrapping Logic
# ==============================================================================


async def _upsert_arms_to_graph(arms_to_create: list[dict], family_id: str):
    """Generic function to upsert a list of PolicyArm nodes into Neo4j."""
    if not arms_to_create:
        log.warning(f"[{family_id}] No arms to upsert.")
        return
    upsert_query = """
    UNWIND $arms AS arm_data
    MERGE (a:PolicyArm {id: arm_data.id})
    SET a.family_id = arm_data.family_id,
        a.description = arm_data.description,
        a.tags = arm_data.tags,
        a.policy_graph_meta = arm_data.policy_graph_meta_str,
        a.embedding = arm_data.embedding,
        a.updated_ts = timestamp()
    """
    await cypher_query(upsert_query, {"arms": arms_to_create})
    log.info(
        f"[{family_id}] Successfully upserted {len(arms_to_create)} semantically-indexed arms into the graph.",
    )


async def _bootstrap_tool_family() -> None:
    """Discovers, embeds, and upserts all executable Simula tools."""
    family_id = "simula.agent.tools"
    log.info(f"[{family_id}] Starting bootstrapping...")
    tools_with_meta = get_tracked_tools()
    if not tools_with_meta:
        log.warning(f"[{family_id}] No tools found. Skipping.")
        return

    docs = {
        name: _create_embedding_document_for_tool(name, meta)
        for name, meta in tools_with_meta.items()
    }
    embedding_tasks = {
        name: get_embedding(doc, task_type="RETRIEVAL_DOCUMENT")
        for name, doc in docs.items()
        if doc
    }
    embeddings = await asyncio.gather(*embedding_tasks.values())
    tool_embeddings = dict(zip(embedding_tasks.keys(), embeddings))

    arms_to_create = []
    for tool_name, meta in tools_with_meta.items():
        if tool_name not in tool_embeddings or not meta.get("func"):
            continue
        tool_modes = meta.get("modes", ["general"])
        policy_graph_meta = {
            "tool_name": tool_name,
            "tool_modes": tool_modes,
            "parameters_schema": _generate_json_schema_for_tool(meta["func"]),
        }
        arms_to_create.append(
            {
                "id": f"simula.agent.tools.{tool_name}",
                "family_id": family_id,
                "description": inspect.getdoc(meta["func"])
                or f"Directly executes the Simula tool: {tool_name}",
                "tags": ["simula", "tool-api", tool_name] + [f"mode::{m}" for m in tool_modes],
                "policy_graph_meta_str": json.dumps(policy_graph_meta),
                "embedding": tool_embeddings[tool_name],
            },
        )
    await _upsert_arms_to_graph(arms_to_create, family_id)


async def _bootstrap_deliberation_families() -> None:
    """Embeds and upserts all declarative cognitive agents."""
    log.info("[simula.agent.deliberation] Starting bootstrapping for cognitive agents...")
    agent_defs = DELIBERATION_AGENTS

    docs = {agent["arm_id"]: agent["description"] for agent in agent_defs}
    embedding_tasks = {
        name: get_embedding(doc, task_type="RETRIEVAL_DOCUMENT") for name, doc in docs.items()
    }
    embeddings = await asyncio.gather(*embedding_tasks.values())
    agent_embeddings = dict(zip(embedding_tasks.keys(), embeddings))

    arms_to_create = []
    for agent in agent_defs:
        arm_id = agent["arm_id"]
        if arm_id not in agent_embeddings:
            continue
        arms_to_create.append(
            {
                "id": arm_id,
                "family_id": agent["family_id"],
                "description": agent["description"],
                "tags": agent["tags"],
                "policy_graph_meta_str": json.dumps(agent.get("policy_graph_meta", {})),
                "embedding": agent_embeddings[arm_id],
            },
        )
    await _upsert_arms_to_graph(arms_to_create, "simula.agent.deliberation")


async def _create_vector_index() -> None:
    """Ensures the vector index exists in the database for semantic search."""
    index_query = """
    CREATE VECTOR INDEX policyArmIndex IF NOT EXISTS
    FOR (p:PolicyArm) ON (p.embedding)
    OPTIONS { indexConfig: {
        `vector.dimensions`: 768, // Gemini embedding-001 dimension
        `vector.similarity_function`: 'cosine'
    }}
    """
    try:
        await cypher_query(index_query)
        log.info("Successfully created or verified 'policyArmIndex' vector index.")
    except Exception as e:
        log.error(
            f"CRITICAL: FAILED to create vector index 'policyArmIndex'. Manual intervention may be required. Error: {e}",
        )


# ==============================================================================
# 4. Public API for Bootstrapping
# ==============================================================================


async def ensure_simula_agent_families() -> None:
    """
    Public-facing function to run the entire bootstrapping process for all Simula
    agent families (tools and cognitive agents). This should be called once
    during application setup.
    """
    log.info("--- Starting Simula Agent & Tool Family Bootstrapping ---")
    await _bootstrap_tool_family()
    await _bootstrap_deliberation_families()
    await _create_vector_index()
    log.info("--- Simula Agent & Tool Family Bootstrapping Complete ---")
