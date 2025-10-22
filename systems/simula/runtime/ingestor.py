from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re

# Ensure project root in path for direct execution
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.append(str(Path(__file__).resolve().parents[3]))

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

# MODIFIED: Import the public getter function, not the private registry variable.
from systems.simula.code_sim.telemetry import get_tracked_tools

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

VECTOR_INDEX_NAME = "simulaToolIndex"
# Use a dimension size compatible with your embedding model, e.g., 768 for gemini-embedding-001
EMBED_DIM = 768


def _spec_to_json_schema(func: Any) -> dict[str, Any]:
    """
    Introspects a function's signature and docstring to build a JSON schema for its parameters.
    """
    sig = inspect.signature(func)
    schema = {"type": "object", "properties": {}, "required": []}
    doc_params = {}
    if func.__doc__:
        # A more robust regex to find the 'Args:' section
        args_section_match = re.search(
            r"Args:\n(.*?)(Returns:|Raises:|\Z)",
            func.__doc__,
            re.DOTALL,
        )
        if args_section_match:
            param_regex = re.compile(r"^\s*(\w+)\s*:\s*(.*)", re.MULTILINE)
            for match in param_regex.finditer(args_section_match.group(1)):
                doc_params[match.group(1)] = match.group(2).strip()

    for name, param in sig.parameters.items():
        if name in ("cls", "self", "args", "kwargs"):
            continue

        prop = {}
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
            prop["type"] = "string"  # Default for unknown types

        if name in doc_params:
            prop["description"] = doc_params[name]

        schema["properties"][name] = prop
        if param.default is inspect.Parameter.empty:
            schema["required"].append(name)

    return schema


def _content_hash_for(node_props: dict[str, Any]) -> str:
    """Creates a stable hash for the tool's definition."""
    s = json.dumps(
        {k: node_props[k] for k in sorted(node_props.keys()) if k != "embedding"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def _ensure_vector_index() -> None:
    """Creates the Neo4j vector index if it doesn't already exist."""
    await cypher_query(
        f"""
        CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
        FOR (t:SimulaTool) ON (t.embedding)
        OPTIONS {{
          indexConfig: {{
            `vector.dimensions`: {EMBED_DIM},
            `vector.similarity_function`: 'cosine'
          }}
        }}
        """,
    )
    logger.info(f"Vector index '{VECTOR_INDEX_NAME}' ensured at {EMBED_DIM} dims.")


async def _load_existing_hashes() -> dict[str, str]:
    """Fetches content hashes of existing tools to avoid redundant updates."""
    rows = await cypher_query("MATCH (t:SimulaTool) RETURN t.name AS name, t.content_hash AS hash")
    return {r["name"]: r["hash"] for r in (rows or []) if r.get("name") and r.get("hash")}


async def synchronize_simula_tool_catalog() -> None:
    """
    Extracts decorated Simula tools, embeds them, and upserts into Neo4j
    for semantic retrieval during agent planning.
    """
    print("➡️  Simula: Synchronizing Tool Catalog with Neo4j...")

    try:
        await _ensure_vector_index()
    except Exception as e:
        logger.error(f"🔥 CRITICAL: Failed to ensure vector index: {e}")
        return

    # Dynamically import to ensure decorators have run and populated the registry
    from systems.simula.nscs import agent_tools

    # MODIFIED: Use the public getter function to retrieve the full tool registry with metadata
    tools_with_meta = get_tracked_tools()

    if not tools_with_meta:
        logger.error(
            "🔥 CRITICAL: Tool registry is empty. Ensure agent_tools.py is imported and decorators are running.",
        )
        return

    logger.info(f"Discovered {len(tools_with_meta)} Simula tools via decorator registry.")

    try:
        existing_hashes = await _load_existing_hashes()
    except Exception as e:
        logger.error(f"🔥 CRITICAL: Could not fetch existing SimulaTool hashes: {e}")
        return

    updated_count = 0
    # MODIFIED: The loop now correctly unpacks the metadata dictionary.
    for tool_name, meta in tools_with_meta.items():
        try:
            # MODIFIED: Extract the function and modes from the meta dictionary.
            func = meta.get("func")
            modes = meta.get("modes", ["general"])

            # Safety check to ensure we have a callable function.
            if not func or not callable(func):
                logger.error(f"⚠️ Tool '{tool_name}' in registry is not a valid callable. Skipping.")
                continue

            description = inspect.getdoc(func) or f"Simula tool: {tool_name}"
            # This line was the source of the error. It now receives the correct 'func' object.
            parameters_schema = _spec_to_json_schema(func)

            node_props = {
                "name": tool_name,
                "description": description.strip(),
                "parameters": json.dumps(parameters_schema),
                "modes": modes,  # MODIFIED: Add modes to the node properties
                "returns": json.dumps(
                    {"type": "object", "description": "The result of the tool execution."},
                ),
                "safety": 1.0,
            }

            content_hash = _content_hash_for(node_props)
            if existing_hashes.get(tool_name) == content_hash:
                continue

            # MODIFIED: Compose rich text for embedding, now including modes.
            embed_text = (
                f"Tool Name: {tool_name}\nModes: {', '.join(modes)}\nPurpose: {description}"
            )
            embedding = await get_embedding(embed_text, task_type="RETRIEVAL_DOCUMENT")

            params_to_upsert = {**node_props, "content_hash": content_hash, "embedding": embedding}

            # MODIFIED: Update Cypher query to include the 'modes' property.
            await cypher_query(
                """
                MERGE (t:SimulaTool {name: $name})
                SET t += {
                    description: $description,
                    parameters: $parameters,
                    modes: $modes,
                    returns: $returns,
                    safety: $safety,
                    content_hash: $content_hash,
                    embedding: $embedding,
                    last_updated: datetime()
                }
                """,
                params_to_upsert,
            )
            updated_count += 1
            logger.info(f"✅ Upserted SimulaTool '{tool_name}'.")
        except Exception as e:
            logger.error(f"🔥 FAILED to upsert SimulaTool '{tool_name}': {e}", exc_info=True)

    print(
        f"✅ Simula Tool Catalog synchronized. Updated: {updated_count}, Total: {len(tools_with_meta)}",
    )


if __name__ == "__main__":
    # Allows running the script directly for manual syncs
    # python -m systems.simula.runtime.ingestor
    asyncio.run(synchronize_simula_tool_catalog())
