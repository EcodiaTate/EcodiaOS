# systems/synk/core/tools/schema_bootstrap.py
from __future__ import annotations

import asyncio
from collections.abc import Iterable

from core.utils.neo.cypher_query import cypher_query
from core.utils.neo.neo_driver import close_driver, init_driver  # for standalone script usage only
from systems.synk.core.tools.vector_store import create_vector_index

"""
Driverless + Centralized-Endpoints compliant:
- All graph I/O goes through cypher_query(...)
- No direct driver/session usage in helpers
- init_driver/close_driver only used when running this file as a script
"""

NON_VECTOR_DDL: list[str] = [
    # Events
    "CREATE CONSTRAINT event_by_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
    "CREATE INDEX event_by_created_at IF NOT EXISTS FOR (e:Event) ON (e.created_at)",
    "CREATE INDEX event_by_cluster IF NOT EXISTS FOR (e:Event) ON (e.cluster_id)",
    # Tools
    "CREATE INDEX tool_by_name IF NOT EXISTS FOR (t:Tool) ON (t.name)",
    # Clusters
    "CREATE CONSTRAINT cluster_by_key IF NOT EXISTS FOR (c:Cluster) REQUIRE c.cluster_key IS UNIQUE",
    "CREATE INDEX cluster_by_run IF NOT EXISTS FOR (c:Cluster) ON (c.run_id)",
]


async def _apply_all(queries: Iterable[str]) -> None:
    # DRIVERLESS: execute via cypher_query
    for q in queries:
        await cypher_query(q)


async def _ensure_vector_indexes() -> None:
    """
    Create vector indexes using the shared helper (already driverless).
    """
    # If create_vector_index signature changes, we keep simple calls without driver.
    await create_vector_index(label="Event", prop="vector_gemini", dims=3072, sim="cosine")
    await create_vector_index(
        label="Cluster",
        prop="cluster_vector_gemini",
        dims=3072,
        sim="cosine",
    )


async def ensure_schema() -> None:
    await _apply_all(NON_VECTOR_DDL)
    await _ensure_vector_indexes()


async def main() -> None:
    # Standalone run: init & close the shared async driver around operations
    await init_driver()
    try:
        await ensure_schema()
    finally:
        await close_driver()


if __name__ == "__main__":
    asyncio.run(main())
