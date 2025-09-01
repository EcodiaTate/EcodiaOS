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

# Benign Neo4j DDL errors we treat as success (keep health green on re-runs)
_BENIGN = (
    "Neo.ClientError.Schema.ConstraintAlreadyExists",
    "Neo.ClientError.Schema.ConstraintWithNameAlreadyExists",
    "Neo.ClientError.Schema.EquivalentSchemaRuleAlreadyExists",
    "Neo.ClientError.Schema.IndexAlreadyExists",
    "Neo.ClientError.Schema.EquivalentSchemaIndexAlreadyExists",
)

async def _run_ddl(stmt: str) -> None:
    try:
        await cypher_query(stmt)
    except Exception as e:
        msg = f"{e}"
        if any(code in msg for code in _BENIGN):
            # Idempotent success
            return
        raise

async def _apply_all(queries: Iterable[str]) -> None:
    for q in queries:
        await _run_ddl(q)

# --- One-time migrations / cleanup for legacy names & shapes ---------------------
MIGRATION_DDL: list[str] = [
    # Old UNIQUE on (agent,name) — superseded by NODE KEY
    "DROP CONSTRAINT profile_agent_name IF EXISTS",
    "DROP CONSTRAINT profile_key IF EXISTS",
]

# --- Canonical schema (non-vector) ----------------------------------------------
NON_VECTOR_DDL: list[str] = [
    # Identity & Governance
    "CREATE CONSTRAINT profile_unique IF NOT EXISTS FOR (p:Profile) REQUIRE (p.agent, p.name) IS NODE KEY",
    "CREATE CONSTRAINT facet_id_unique IF NOT EXISTS FOR (f:Facet) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT constitution_rule_id IF NOT EXISTS FOR (r:ConstitutionRule) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT consrule_name IF NOT EXISTS FOR (r:ConstitutionRule) REQUIRE r.name IS UNIQUE",
    "CREATE CONSTRAINT ingeststate_id IF NOT EXISTS FOR (s:IngestState) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT ingesthistory_commit IF NOT EXISTS FOR (h:IngestHistory) REQUIRE h.commit_id IS UNIQUE",

    # Policy Arms (mirror seeder)
    "CREATE CONSTRAINT policyarm_id IF NOT EXISTS FOR (p:PolicyArm) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT policyarm_armid IF NOT EXISTS FOR (p:PolicyArm) REQUIRE p.arm_id IS UNIQUE",

    # Events
    "CREATE CONSTRAINT event_by_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
    "CREATE INDEX event_by_created_at IF NOT EXISTS FOR (e:Event) ON (e.created_at)",
    "CREATE INDEX event_by_cluster IF NOT EXISTS FOR (e:Event) ON (e.cluster_id)",

    # Tools
    "CREATE INDEX tool_by_name IF NOT EXISTS FOR (t:Tool) ON (t.name)",

    # Clusters
    "CREATE CONSTRAINT cluster_by_key IF NOT EXISTS FOR (c:Cluster) REQUIRE c.cluster_key IS UNIQUE",
    "CREATE INDEX cluster_by_run IF NOT EXISTS FOR (c:Cluster) ON (c.run_id)",

    # WM/Code graph bits surfaced in your logs
    "CREATE CONSTRAINT adr_path IF NOT EXISTS FOR (a:ArchitecturalDecision) REQUIRE a.path IS UNIQUE",
    "CREATE CONSTRAINT codefile_path IF NOT EXISTS FOR (cf:CodeFile) REQUIRE cf.path IS UNIQUE",
]

# --- Vector indexes --------------------------------------------------------------
async def _ensure_vector_indexes() -> None:
    """Create vector indexes using the shared helper (driverless)."""
    await create_vector_index(label="Event",         prop="vector_gemini",        dims=3072, sim="cosine")
    await create_vector_index(label="Cluster",       prop="cluster_vector_gemini",dims=3072, sim="cosine")
    await create_vector_index(label="Deliberation",  prop="embedding",            dims=3072, sim="cosine")

# --- Small bootstrap for ingest state (silences UnknownLabel/Property warnings) --
async def _ensure_ingest_state(state_id: str = "default") -> None:
    await cypher_query(
        """
        MERGE (s:IngestState {id:$id})
        ON CREATE SET
          s.created_at = datetime(),
          s.last_commit = null
        """,
        {"id": state_id},
    )

# --- Public entrypoints ----------------------------------------------------------
async def ensure_schema() -> None:
    # 1) Run migrations first so new creates won’t conflict
    await _apply_all(MIGRATION_DDL)

    # 2) Create constraints/indexes idempotently
    await _apply_all(NON_VECTOR_DDL)

    # 3) Seed ingest state (prevents UnknownLabel/Property warnings in readers)
    await _ensure_ingest_state("default")

    # 4) Vector indexes
    await _ensure_vector_indexes()

async def main() -> None:
    # Standalone run: init & close the shared async driver around operations
    await init_driver()
    try:
        await ensure_schema()
        print("✅ Schema bootstrap complete.")
    finally:
        await close_driver()

if __name__ == "__main__":
    asyncio.run(main())
