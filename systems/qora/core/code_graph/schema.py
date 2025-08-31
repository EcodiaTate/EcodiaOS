# systems/qora/core/code_graph/schema.py
# --- GOD-LEVEL UPGRADE (FINAL) ---
from __future__ import annotations
from core.utils.neo.cypher_query import cypher_query

VECTOR_DIM = 3072 # As defined in embeddings_gemini.py

async def ensure_all_graph_indices() -> dict[str, str]:
    """
    Establishes all necessary constraints and indexes for Qora's god-level graph.
    This includes nodes for code, libraries, conflicts, deliberations, and architectural decisions.
    This function is idempotent and safe to run on startup.
    """
    cyphers = {
        # --- Code Graph Indexes ---
        "code_fqn_constraint": "CREATE CONSTRAINT code_fqn IF NOT EXISTS FOR (n:Code) REQUIRE n.fqn IS UNIQUE",
        "code_embedding_index": f"""
            CREATE VECTOR INDEX code_embedding IF NOT EXISTS
            FOR (n:Code) ON (n.embedding)
            OPTIONS {{ indexConfig: {{ `vector.dimensions`: {VECTOR_DIM}, `vector.similarity_function`: 'cosine' }} }}
            """,
        "code_fts_index": """
            CREATE FULLTEXT INDEX code_fts IF NOT EXISTS
            FOR (n:Code) ON EACH [n.name, n.path, n.docstring]
            """,
        
        # --- Library Node Constraint ---
        "library_name_constraint": "CREATE CONSTRAINT library_name IF NOT EXISTS FOR (l:Library) REQUIRE l.name IS UNIQUE",
        
        # --- Conflict Learning Indexes ---
        "conflict_uuid_constraint": "CREATE CONSTRAINT conflict_uuid IF NOT EXISTS FOR (c:Conflict) REQUIRE c.uuid IS UNIQUE",
        "conflict_embedding_index": f"""
            CREATE VECTOR INDEX conflict_embedding IF NOT EXISTS
            FOR (c:Conflict) ON (c.embedding)
            OPTIONS {{ indexConfig: {{ `vector.dimensions`: {VECTOR_DIM}, `vector.similarity_function`: 'cosine' }} }}
            """,
            
        # --- NEW: Multi-Modal Context Indexes ---
        "deliberation_id_constraint": "CREATE CONSTRAINT deliberation_id IF NOT EXISTS FOR (d:Deliberation) REQUIRE d.deliberation_id IS UNIQUE",
        "adr_path_constraint": "CREATE CONSTRAINT adr_path IF NOT EXISTS FOR (a:ArchitecturalDecision) REQUIRE a.path IS UNIQUE",
        "deliberation_embedding_index": f"""
            CREATE VECTOR INDEX deliberation_embedding IF NOT EXISTS
            FOR (d:Deliberation) ON (d.embedding)
            OPTIONS {{ indexConfig: {{ `vector.dimensions`: {VECTOR_DIM}, `vector.similarity_function`: 'cosine' }} }}
            """,
        "codefile_path_constraint": "CREATE CONSTRAINT codefile_path IF NOT EXISTS FOR (cf:CodeFile) REQUIRE cf.path IS UNIQUE",
    }

    results = {}
    for name, query in cyphers.items():
        try:
            await cypher_query(query)
            results[name] = "Applied"
        except Exception as e:
            results[name] = f"Failed or already exists: {e!r}"
            
    return results