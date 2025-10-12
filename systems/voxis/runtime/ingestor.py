from __future__ import annotations

import asyncio
import hashlib
import json
import logging

# Ensure project root is in path for imports
import sys
from pathlib import Path

import yaml

sys.path.append(str(Path(__file__).resolve().parents[2]))

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parents[3] / "config" / "catalog.voxisTools.yaml"
VECTOR_INDEX_NAME = "voxisToolIndex"


async def synchronize_tool_catalog():
    """
    Reads the tool catalog from YAML, creates a dedicated vector index, and
    intelligently syncs any new or changed tools to the Neo4j database.
    """
    print("➡️ Step 1.2: Synchronizing Tool Catalog with Neo4j...")

    # 1. Ensure the vector index for :VoxisTool exists.
    try:
        # NOTE: Changed vector.dimensions to 3072 to match your embeddings_gemini.py file.
        # This is the critical fix.
        await cypher_query(
            f"""
            CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
            FOR (t:VoxisTool) ON (t.embedding)
            OPTIONS {{ indexConfig: {{
                `vector.dimensions`: 3072,
                `vector.similarity_function`: 'cosine'
            }} }}
            """,
        )
        logger.info(f"Vector index '{VECTOR_INDEX_NAME}' is present for 3072 dimensions.")
    except Exception as e:
        logger.error(f"🔥 CRITICAL: Failed to ensure vector index exists: {e}")
        return

    # 2. Load Tool Definitions from YAML
    if not CATALOG_PATH.exists():
        logger.error(f"🔥 CRITICAL: Catalog file not found at {CATALOG_PATH}")
        return

    with open(CATALOG_PATH, encoding="utf-8") as f:
        endpoints = yaml.safe_load(f).get("endpoints", [])

    if not endpoints:
        logger.warning("No tool endpoints found in catalog.yaml.")
        return
    logger.info(f"Found {len(endpoints)} tool definitions in YAML.")

    # 3. Get existing tools from DB to check for changes
    try:
        result = await cypher_query("MATCH (t:VoxisTool) RETURN t.id AS id, t.content_hash AS hash")
        existing_tools = {row["id"]: row["hash"] for row in result}
    except Exception as e:
        logger.error(f"🔥 CRITICAL: Could not fetch existing tools from Neo4j: {e}")
        return

    # 4. Process and sync each tool
    for tool in endpoints:
        tool_id = f"{tool.get('driver_name')}.{tool.get('endpoint')}"
        tool_content_str = json.dumps(tool, sort_keys=True)
        content_hash = hashlib.sha256(tool_content_str.encode("utf-8")).hexdigest()

        if existing_tools.get(tool_id) == content_hash:
            continue

        logger.info(f"Syncing new or updated tool: {tool_id}...")
        try:
            desc_text = f"Tool: {tool.get('title', '')}. Description: {tool.get('description', '')}. Tags: {', '.join(tool.get('tags', []))}"
            embedding = await get_embedding(desc_text)

            params = {
                "tool_id": tool_id,
                "content_hash": content_hash,
                "driver_name": tool.get("driver_name"),
                "endpoint": tool.get("endpoint"),
                "mode": tool.get("mode"),
                "title": tool.get("title"),
                "description": tool.get("description"),
                "tags": tool.get("tags", []),
                "arg_schema_json": json.dumps(tool.get("arg_schema", {})),
                "defaults_json": json.dumps(tool.get("defaults", {})),
                "embedding": embedding,
            }

            await cypher_query(
                """
                MERGE (t:VoxisTool {id: $tool_id})
                SET t += {
                    content_hash: $content_hash,
                    driver_name: $driver_name,
                    endpoint: $endpoint,
                    mode: $mode,
                    title: $title,
                    description: $description,
                    tags: $tags,
                    arg_schema_json: $arg_schema_json,
                    defaults_json: $defaults_json,
                    embedding: $embedding,
                    last_updated: datetime()
                }
                """,
                params,
            )
            logger.info(f"✅ Ingested '{tool_id}' as :VoxisTool into Neo4j.")
        except Exception as e:
            logger.error(f"🔥 FAILED to ingest tool '{tool_id}': {e}", exc_info=True)

    print("✅ Tool Catalog synchronized.")
