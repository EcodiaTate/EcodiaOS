# /app/core/utils/neo/seeding.py
from __future__ import annotations

import logging
from typing import Any

from core.utils.neo.cypher_query import cypher_query
from scripts.seed_flags import SEED_FLAGS, upsert_flag # Re-use our existing logic

async def seed_initial_flags():
    """
    Checks if flags exist and seeds them if the database is empty.
    This function is idempotent and safe to run on every startup.
    """
    try:
        logging.info("Checking for initial feature flags...")
        
        # Check if any flags already exist to avoid re-running every time
        existing_flags = await cypher_query("MATCH (f:Flag) RETURN count(f) as count")
        if existing_flags and existing_flags[0].get("count", 0) > 0:
            logging.info("Flags already exist. Skipping seeding.")
            return

        logging.info("No flags found. Seeding initial data...")
        for flag_data in SEED_FLAGS:
            await upsert_flag(flag_data)
        
        logging.info("✅ Initial flag seeding complete.")

    except Exception as e:
        logging.error(f"❌ Critical error during initial data seeding: {e}", exc_info=True)
        # Depending on your needs, you might want to raise the exception
        # to prevent the server from starting in a bad state.
        # raise e