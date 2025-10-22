from __future__ import annotations

import asyncio
import json
import os

from core.utils.neo.cypher_query import cypher_query
from core.utils.neo.neo_driver import close_driver, init_driver
from systems.synk.core.tools.schema_bootstrap import ensure_schema


async def seed_profiles():
    """
    Ensures the required :Profile nodes exist in the database.
    This is idempotent and safe to run multiple times.
    """
    print("Seeding agent profiles...")

    # Simula Profile (Modern Schema)
    await cypher_query(
        """
        MERGE (p:Profile {agent: 'simula', name: 'prod'})
        SET
          p.rule_ids = $rule_ids,
          p.facet_ids = $facet_ids,
          p.settings_json = $settings_json
        """,
        {
            "rule_ids": ["CR_PROHIBITED_VIOLENCE"],
            "facet_ids": ["F_SIMULA_CORE_V1"],
            "settings_json": "{}",
        },
    )

    # Evo Profile (Corrected to Modern Schema)
    await cypher_query(
        """
        MERGE (p:Profile {agent: 'evo', name: 'prod'})
        SET
          p.rule_ids = [],
          p.facet_ids = [],
          p.settings_json = $settings_json
        """,
        {
            "settings_json": json.dumps(
                {
                    "max_tokens": 2000,
                    "temperature_cap": 0.7,
                    "tools": {
                        "allowed": [
                            "conflict.read",
                            "nova.propose",
                            "nova.evaluate",
                            "nova.auction",
                        ],
                    },
                },
            ),
        },
    )
    print("Agent profiles seeded successfully.")


async def main():
    """
    Main entry point for the seeder script.
    """
    print("--- Starting Database Seeding ---")
    try:
        await init_driver()
        print("Ensuring database schema...")
        await ensure_schema()
        print("Schema ensured.")
        await seed_profiles()
    except Exception as e:
        print(f"An error occurred during seeding: {e}")
        # Exit with a non-zero code to indicate failure
        exit(1)
    finally:
        await close_driver()
    print("--- Database Seeding Complete ---")


if __name__ == "__main__":
    # Load environment variables from .env file if available
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv())

    asyncio.run(main())
