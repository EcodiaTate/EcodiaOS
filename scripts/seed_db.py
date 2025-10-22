# seed_db.py (refactored for robustness and clarity)
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from typing import Optional

from core.utils.neo.cypher_query import cypher_query
from core.utils.neo.neo_driver import close_driver, init_driver

# FIX: Import the lightweight, dependency-free list of tool names DIRECTLY.
# This is the crucial change that severs the dependency on heavy application code.
from systems.simula.agent.tool_names import CANONICAL_TOOL_NAMES
from systems.synapse.policy.policy_dsl import PolicyGraph, PolicyNode

# --- Constants ---
SIMULA_AGENT_NAME = "Simula"
DEFAULT_NEO4J_URI = "neo4j://neo4j:7687"

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)


# --- Helpers ---


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def _mask_password(pwd: str | None) -> str:
    if not pwd:
        return "<unset>"
    return pwd[:2] + "***" + pwd[-2:] if len(pwd) > 4 else "***"


# --- Database Operations ---


async def wait_for_neo4j(max_wait_s: int = 120, interval_s: float = 1.5) -> None:
    """Waits for the Neo4j database to become responsive."""
    logger.info("Waiting for Neo4j to be ready...")
    t0 = time.time()
    for attempt in range(1, int(max_wait_s / interval_s) + 2):
        try:
            await asyncio.wait_for(cypher_query("RETURN 1"), timeout=10)
            if attempt > 1:
                logger.info(f"Neo4j is ready after {attempt} attempts ({time.time() - t0:.1f}s).")
            return
        except Exception as e:
            if time.time() - t0 > max_wait_s:
                raise TimeoutError(f"Neo4j not ready after {max_wait_s}s: {e}") from e
            await asyncio.sleep(interval_s)


def get_simula_tool_names() -> list[str]:
    """
    Returns the canonical list of Simula tool names from the single source of truth.
    """
    if not CANONICAL_TOOL_NAMES:
        raise ImportError("Canonical tool name list is empty or could not be imported.")
    return sorted(list(set(CANONICAL_TOOL_NAMES)))  # Use set to auto-dedupe aliases


def create_seed_policy_graph(name: str) -> dict:
    """Creates a safe, default policy graph using the canonical Pydantic model."""
    graph = PolicyGraph(
        version=1,
        id=f"pg::{name}",
        nodes=[
            PolicyNode(
                id="prompt",
                type="prompt",
                model="gpt-3.5-turbo",
                params={"temperature": 0.15},
            ),
        ],
        meta={"seeded": True, "arm": name},
    )
    return graph.model_dump(mode="json")


# --- Seeding Function (Data Only) ---


async def seed_simula_policy_arms():
    """Seeds the database with PolicyArm nodes for all canonical Simula tools."""
    tool_names = get_simula_tool_names()
    logger.info(f"Found {len(tool_names)} canonical Simula tools to seed as PolicyArms.")

    # This query ensures the Agent and its core Facet/Profile exist before creating arms.
    # It's idempotent and won't cause conflicts.
    await cypher_query(
        """
        MERGE (a:Agent {name: $agent_name})
          ON CREATE SET a.summary='Autonomous code evolution agent.', a.created_at=datetime()
        MERGE (f:Facet {id: 'F_SIMULA_CORE_V1'})
          ON CREATE SET f.title='Simula Core Identity', f.name='Simula Core Identity', f.text='You are Simula...'
        MERGE (p:Profile {agent: $agent_name, name:'prod'})
        MERGE (r:ConstitutionRule {name:'Base Safety'})
          ON CREATE SET r.text='Base constitution rule (seed)', r.priority=100, r.active=true
        MERGE (a)-[:HAS_FACET]->(f)
        MERGE (p)-[:INCLUDES]->(r)
        """,
        {"agent_name": SIMULA_AGENT_NAME},
    )

    arm_data = [
        {"name": n, "graph_json": json.dumps(create_seed_policy_graph(n))} for n in tool_names
    ]

    # This MERGE query will create or update the PolicyArm nodes.
    await cypher_query(
        """
        UNWIND $arms AS arm_data
        MERGE (a:PolicyArm {id: arm_data.name})
        ON CREATE SET
            a.mode='planful',
            a.policy_graph=arm_data.graph_json,
            a.created_at=datetime()
        ON MATCH SET
            a.policy_graph=arm_data.graph_json,
            a.updated_at=datetime()
        """,
        {"arms": arm_data},
    )


# --- Main Orchestrator ---


async def run_step(name: str, coro):
    """Utility to run and log a single seeding step."""
    logger.info(f"[STEP] {name}...")
    try:
        await coro
        logger.info(f"[STEP] {name} ✓")
    except Exception as e:
        logger.error(f"[STEP] {name} ✗ FAILED: {type(e).__name__}: {e}")
        raise


async def main():
    """Main function to connect to and seed the database."""
    uri = _env("NEO4J_URI", DEFAULT_NEO4J_URI)
    user = _env("NEO4J_USERNAME")
    pwd = _env("NEO4J_PASSWORD")

    logger.info("--- Starting Database Seeding ---")
    logger.info(f"[CFG] NEO4J_URI={uri}")
    logger.info(f"[CFG] user={user or '<unset>'}, pass={_mask_password(pwd)}")

    try:
        await init_driver()
        await run_step("Wait for Neo4j", wait_for_neo4j())
        # The app's startup (`ensure_schema`) will handle constraints.
        # This script now only seeds the PolicyArm data.

    except Exception:
        logger.critical("FATAL: A step failed during database seeding. See logs for details.")
        sys.exit(1)
    finally:
        await close_driver()
    logger.info("--- Database Seeding Complete ---")


if __name__ == "__main__":
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv())
    asyncio.run(main())
