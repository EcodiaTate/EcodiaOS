# seed_db.py (diagnostic + resilient)
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import socket
from typing import Iterable, Optional
from urllib.parse import urlparse

from core.utils.neo.neo_driver import init_driver, close_driver
from core.utils.neo.cypher_query import cypher_query

try:
    from systems.synk.core.tools.schema_bootstrap import ensure_schema as shared_ensure_schema  # type: ignore
except Exception:
    shared_ensure_schema = None  # type: ignore

BENIGN = (
    "Neo.ClientError.Schema.ConstraintAlreadyExists",
    "Neo.ClientError.Schema.ConstraintWithNameAlreadyExists",
    "Neo.ClientError.Schema.EquivalentSchemaRuleAlreadyExists",
    "Neo.ClientError.Schema.IndexAlreadyExists",
    "Neo.ClientError.Schema.EquivalentSchemaIndexAlreadyExists",
)

def log(msg: str) -> None:
    print(msg, flush=True)

def _env(name: str, default: Optional[str] = None) -> str | None:
    return os.getenv(name, default)

def _mask(s: str | None) -> str:
    if not s:
        return "<unset>"
    if len(s) <= 6:
        return "***"
    return s[:2] + "***" + s[-2:]

async def run_ddl(stmt: str, step: str = "ddl") -> None:
    try:
        await asyncio.wait_for(cypher_query(stmt), timeout=30)
    except Exception as e:
        msg = f"{e}"
        if any(code in msg for code in BENIGN):
            log(f"[{step}] benign → {stmt}")
            return
        raise

async def ping_db() -> None:
    await asyncio.wait_for(cypher_query("RETURN 1 AS ok"), timeout=10)

def tcp_probe_from_neo4j_uri(uri: str) -> tuple[str, int]:
    """
    neo4j://host:7687 or bolt://host:7687 → (host, port)
    """
    parsed = urlparse(uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 7687
    return host, port

def tcp_check(host: str, port: int, timeout_s: float = 3.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, "ok"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

async def wait_for_neo4j(max_wait_s: int = 120, interval_s: float = 1.5) -> None:
    t0 = time.time()
    attempt = 0
    while True:
        attempt += 1
        try:
            await ping_db()
            if attempt > 1:
                log(f"[NEO4J] ready after {attempt} attempts, {time.time()-t0:.1f}s")
            return
        except Exception as e:
            if time.time() - t0 > max_wait_s:
                raise TimeoutError(f"Neo4j not ready after {max_wait_s}s: {e}") from e
            await asyncio.sleep(interval_s)

def safe_policy_graph(name: str) -> dict:
    return {
        "version": 1,
        "id": f"pg::{name}",
        "nodes": [{"id": "prompt", "type": "prompt", "model": "gpt-4o-mini", "params": {"temperature": 0.15}}],
        "edges": [],
        "constraints": [],
        "meta": {"seeded": True, "arm": name},
    }

def get_simula_tool_names() -> list[str]:
    try:
        from systems.simula.agent.tool_registry import TOOLS  # type: ignore
        return sorted(set(TOOLS.keys()))
    except Exception:
        return ["get_context_dossier", "apply_refactor_smart", "write_code", "run_tests", "read_file", "list_repo_files"]

# ---------------- Schema ----------------

# inside seed_db.py

async def seed_constraints_and_indexes():
    # Remove legacy/enterprise-only forms if present
    await run_ddl("DROP CONSTRAINT profile_unique IF EXISTS")           # drop NODE KEY if it exists anywhere
    await run_ddl("DROP CONSTRAINT profile_key IF EXISTS")              # legacy name
    await run_ddl("DROP CONSTRAINT profile_agent_name IF EXISTS")       # legacy name

    stmts = [
        # Profiles / Identity — Community-friendly composite UNIQUE
        "CREATE CONSTRAINT profile_identity IF NOT EXISTS "
        "FOR (p:Profile) REQUIRE (p.agent, p.name) IS UNIQUE",

        "CREATE CONSTRAINT facet_id_unique IF NOT EXISTS FOR (f:Facet) REQUIRE f.id IS UNIQUE",
        "CREATE CONSTRAINT consrule_name  IF NOT EXISTS FOR (c:ConstitutionRule) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT agent_name     IF NOT EXISTS FOR (a:Agent) REQUIRE a.name IS UNIQUE",

        # Policy Arms
        "CREATE CONSTRAINT policyarm_id    IF NOT EXISTS FOR (a:PolicyArm) REQUIRE a.id IS UNIQUE",
        "CREATE CONSTRAINT policyarm_armid IF NOT EXISTS FOR (a:PolicyArm) REQUIRE a.arm_id IS UNIQUE",

        # Rules
        "CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:Rule) REQUIRE r.id IS UNIQUE",

        # Code graph basics
        "CREATE CONSTRAINT codefile_path IF NOT EXISTS FOR (cf:CodeFile) REQUIRE cf.path IS UNIQUE",

        # Ingest state
        "CREATE CONSTRAINT ingeststate_id IF NOT EXISTS FOR (s:IngestState) REQUIRE s.id IS UNIQUE",
    ]
    for s in stmts:
        await run_ddl(s)


async def ensure_ingest_states():
    """
    Ensure ingest-state rows exist AND that `last_commit` property key is materialized.
    Using '' (empty string) avoids Neo4j's UnknownPropertyKeyWarning on first reads.
    """
    ids = {os.getenv("QORA_INGEST_STATE_ID", "wm"), "default"}

    # Create rows; set last_commit to '' on create so the key exists
    await cypher_query(
        """
        UNWIND $ids AS sid
        MERGE (s:IngestState {id:sid})
        ON CREATE SET
          s.created_at = datetime(),
          s.last_commit = ''
        """,
        {"ids": list(ids)},
    )

    # Backfill any legacy NULLs to '' so future reads don't warn
    await cypher_query(
        """
        MATCH (s:IngestState)
        WHERE s.last_commit IS NULL
        SET s.last_commit = ''
        """
    )


# --------------- Seed Data ---------------

async def migrate_policyarm_fields():
    await cypher_query("""
        MATCH (a:PolicyArm)
        WHERE a.policy_graph IS NULL AND a.policy_graph_json IS NOT NULL
        SET a.policy_graph = a.policy_graph_json
    """)
    await cypher_query("""
        MATCH (a:PolicyArm)
        WHERE a.id IS NULL AND a.arm_id IS NOT NULL
        SET a.id = a.arm_id
    """)

async def seed_constitution_graph():
    for agent in ("Simula", "simula"):
        await cypher_query("""
            MERGE (p:Profile {agent:$agent, name:'prod'})
            MERGE (r:ConstitutionRule {name:'Base Safety'})
            ON CREATE SET r.text='Base constitution rule (seed)', r.priority=100, r.active=true, r.created_at=datetime()
            MERGE (p)-[:INCLUDES]->(r)
        """, {"agent": agent})
    await cypher_query("""
        MERGE (a:Profile {agent:'__meta__', name:'placeholder_a'})
        MERGE (b:Profile {agent:'__meta__', name:'placeholder_b'})
        MERGE (a)-[:SUPERSEDED_BY]->(b)
    """)

async def seed_rule_key_warmup():
    # Materialize the "max tokens" rule by its unique triple.
    # If a legacy node exists (e.g., id='R_SEED_KEYS'), we reuse it and do NOT change its id.
    await cypher_query(
        """
        MERGE (r:Rule {property:'max_tokens', operator:'<=', value:4096})
        ON CREATE SET
          r.id = 'R_MAX_TOKENS_4096',
          r.rejection_reason = 'Response would exceed maximum token limit.',
          r.created_at = datetime()
        """
    )


async def seed_agent_and_facets():
    await cypher_query("""
        MERGE (a:Agent {name:'Simula'})
        ON CREATE SET a.summary='Autonomous code evolution agent.',
                      a.purpose='Understand, plan, and execute code changes safely.',
                      a.created_at=datetime()
        MERGE (f:Facet {id:'F_SIMULA_CORE_V1'})
        ON CREATE SET f.title='Simula Core Identity',
                      f.text='You are Simula, an autonomous code evolution orchestrator. Your goal is to understand, plan, and execute code changes based on high-level objectives.',
                      f.name='Simula Core Identity'
        SET f.name = coalesce(f.name, f.title)
        MERGE (a)-[:HAS_FACET]->(f)
    """)

async def seed_policy_arms_and_constraints(tool_names: Iterable[str]):
    names = list(tool_names)
    await cypher_query("""
        UNWIND $pairs AS row
        MERGE (a:PolicyArm {id: row.name})
        ON CREATE SET a.arm_id=row.name, a.mode='planful', a.policy_graph=row.graph_json, a.created_at=datetime()
        ON MATCH SET  a.arm_id=row.name, a.mode='planful', a.policy_graph=row.graph_json, a.updated_at=datetime()
    """, {"pairs": [{"name": n, "graph_json": json.dumps(safe_policy_graph(n))} for n in names]})

        # ---- Attach the single "max tokens" Rule to all arms ----
    await cypher_query(
        """
        // Use the unique triple to select the canonical rule node
        MATCH (r:Rule {property:'max_tokens', operator:'<=', value:4096})
        WITH r
        UNWIND $names AS name
        MATCH (a:PolicyArm {id: name})
        MERGE (a)-[:HAS_CONSTRAINT]->(r)
        """,
        {"names": names},
    )


async def seed_reward_metrics_and_config():
    await cypher_query("""
        MERGE (m:RewardMetric {name:'efficiency'}) SET m.weight=0.6, m.type='efficiency'
        MERGE (m2:RewardMetric {name:'safety'})    SET m2.weight=0.4, m.type='safety'
    """)
    await cypher_query("""
        MERGE (c:Config {key:'embedding_defaults'})
        SET c.model='gemini-embedding-001', c.task_type='RETRIEVAL_DOCUMENT', c.dimensions=3072
    """)

async def seed_initial_data():
    await migrate_policyarm_fields()
    await seed_constitution_graph()
    await seed_rule_key_warmup()
    await seed_agent_and_facets()
    await seed_policy_arms_and_constraints(get_simula_tool_names())
    await seed_reward_metrics_and_config()

# --------------- Orchestrator ---------------

async def run_step(name: str, coro, timeout: float | None = None):
    log(f"[STEP] {name} …")
    try:
        res = await asyncio.wait_for(coro, timeout=timeout) if timeout else await coro
        log(f"[STEP] {name} ✓")
        return res
    except Exception as e:
        log(f"[STEP] {name} ✗  {type(e).__name__}: {e}")
        raise

async def main():
    # Print connection info up front
    uri = _env("NEO4J_URI") or _env("NEO4J_URL") or "neo4j://neo4j:7687"
    user = _env("NEO4J_USERNAME") or _env("NEO4J_USER")
    pwd = _env("NEO4J_PASSWORD") or _env("NEO4J_PASS")
    minimal = _env("SEED_MINIMAL") == "1"

    host, port = tcp_probe_from_neo4j_uri(uri)
    ok, why = tcp_check(host, port)
    log(f"[CFG] NEO4J_URI={uri}")
    log(f"[CFG] user={user or '<unset>'}, pass={_mask(pwd)}")
    log(f"[NET] bolt tcp {host}:{port} → {why}")

    log("--- Starting Database Seeding ---")
    try:
        await init_driver()  # uses env creds
        await run_step("wait_for_neo4j", wait_for_neo4j(), timeout=180)

        if shared_ensure_schema and not minimal:
            await run_step("shared.ensure_schema", shared_ensure_schema(), timeout=180)
        else:
            log("[INFO] shared bootstrap skipped (absent or SEED_MINIMAL=1)")

        await run_step("constraints/indexes", seed_constraints_and_indexes(), timeout=180)
        await run_step("ensure_ingest_states", ensure_ingest_states(), timeout=60)

        if minimal:
            log("[INFO] SEED_MINIMAL=1 → skipping heavy seed data")
        else:
            await run_step("seed_initial_data", seed_initial_data(), timeout=300)

    except asyncio.TimeoutError as e:
        log(f"FATAL: step timed out: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"FATAL: unhandled error: {e!r}")
        sys.exit(1)
    finally:
        await close_driver()
    log("--- Database Seeding Complete ---")

if __name__ == "__main__":
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())
    asyncio.run(main())
