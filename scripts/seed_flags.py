# scripts/seed_flags_direct.py
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

# --- Core Application Imports ---
# NOTE: You may need to adjust these paths if you run this script
# from a different directory than your project root.
from core.utils.neo.cypher_query import cypher_query
from core.utils.neo.neo_driver import init_driver, close_driver

# --- Configuration & Data ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Based on analysis of the codebase (route_gate usage)
SEED_FLAGS = [
    {
        "key": "simula.codegen.enabled",
        "type": "bool",
        "value": True,
        "description": "Enables the Simula code generation job endpoint.",
        "component": "simula",
        "reason": "Initial system seeding.",
    },
    {
        "key": "equor.identity.declare.enabled",
        "type": "bool",
        "value": True,
        "description": "Enables the Equor endpoint for declaring identities.",
        "component": "equor",
        "reason": "Initial system seeding.",
    },
    {
        "key": "equor.constitution.update.enabled",
        "type": "bool",
        "value": True,
        "description": "Enables the Equor endpoint for updating the constitution.",
        "component": "equor",
        "reason": "Initial system seeding.",
    },
    {
        "key": "equor.audit.invariants.enabled",
        "type": "bool",
        "value": True,
        "description": "Enables the Equor endpoint for running invariant audits.",
        "component": "equor",
        "reason": "Initial system seeding.",
    },
]

# --- Helper functions (copied from switchboard/flags.py for self-containment) ---

def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)

def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)

def _actor_identity() -> str:
    return os.getenv("IDENTITY_ID", "ecodia.system.seeder")

# --- Main Seeding Logic ---

async def upsert_flag(flag_data: dict[str, Any]):
    """
    Directly upserts a flag and its audit trail into Neo4j
    using the logic from the /switchboard/flags endpoint.
    """
    key = flag_data["key"]
    logging.info(f"  -> Upserting flag: '{key}'...")

    # This Cypher logic is adapted directly from your set_flag endpoint
    cypher_upsert = """
    // Upsert the flag itself
    MERGE (f:Flag {key:$k})
      ON CREATE SET
        f.type = $t,
        f.default_json = coalesce(f.default_json, $v),
        f.description = $d,
        f.state = 'active'
      ON MATCH SET
        f.type = coalesce(f.type, $t),
        f.description = coalesce($d, f.description)
    SET f.value_json = $v, f.updated_at = $now
    WITH f

    // Create the audit trail
    MERGE (i:Identity {key:$actor})
      ON CREATE SET i.created_at = $now
    MERGE (chg:FlagChange {id:$id})
      ON CREATE SET
        chg.key = $k,
        chg.new_json = $v,
        chg.actor = $actor,
        chg.reason = $reason,
        chg.ts = $now
    MERGE (chg)-[:CHANGED_FLAG]->(f)
    MERGE (chg)-[:BY]->(i)
    """
    params = {
        "k": key,
        "t": flag_data.get("type", "json"),
        "v": _to_json(flag_data.get("value")),
        "d": flag_data.get("description"),
        "now": _now_ms(),
        "id": str(uuid4()),
        "actor": _actor_identity(),
        "reason": flag_data.get("reason"),
    }
    await cypher_query(cypher_upsert, params)

    # Link to component if specified
    if component := flag_data.get("component"):
        cypher_component = """
        MATCH (f:Flag {key:$k})
        MERGE (c:Component {name:$c})
        MERGE (f)-[:FOR_COMPONENT]->(c)
        """
        await cypher_query(cypher_component, {"k": key, "c": component})
    
    logging.info(f"  ✅ Successfully upserted '{key}'.")


async def main():
    """Main function to initialize driver, seed flags, and close driver."""
    logging.info("🌱 Starting direct database flag seeding process...")
    try:
        await init_driver()
        logging.info("Neo4j driver initialized.")
        
        for flag_data in SEED_FLAGS:
            await upsert_flag(flag_data)

    except Exception as e:
        logging.error(f"An error occurred during seeding: {e}", exc_info=True)
    finally:
        logging.info("Closing Neo4j driver...")
        await close_driver()
        logging.info("Neo4j driver closed. Seeding complete.")


if __name__ == "__main__":
    # Ensure .env file is loaded if your driver depends on it
    from dotenv import load_dotenv
    # Adjust path to your .env file as needed
    load_dotenv(dotenv_path="./config/.env")
    
    asyncio.run(main())