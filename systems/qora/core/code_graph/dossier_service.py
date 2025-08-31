# systems/qora/core/code_graph/dossier_service.py
# --- GOD-LEVEL UPGRADE (FINAL) ---
from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query

### --- Dossier Building Logic --- ###

async def _get_entry_node(fqn: str) -> dict | None:
    """Finds the primary node for the dossier target."""
    query = f"MATCH (n:Code {{ fqn: $fqn }}) RETURN n"
    results = await cypher_query(query, {"fqn": fqn})
    return results[0] if results else None

async def _get_semantic_neighbors(embedding: list[float], top_k: int) -> list[dict]:
    """Finds semantically similar code using the vector index."""
    query = """
    CALL db.index.vector.queryNodes('code_embedding', $top_k, $embedding)
    YIELD node, score
    RETURN
        node.fqn AS fqn,
        node.name AS name,
        node.path AS path,
        left(node.docstring, 200) AS docstring,
        score
    """
    return await cypher_query(query, {"top_k": top_k, "embedding": embedding})

async def _get_structural_neighbors(fqn: str) -> dict:
    """
    This is Qora's SPECIALIZED structural query, now expanded to find all
    rich relationships including imports, inheritance, and type usage.
    """
    query = """
    MATCH (target:Code { fqn: $fqn })
    // Standard relationships
    OPTIONAL MATCH (caller:Function)-[:CALLS]->(target)
    OPTIONAL MATCH (target)-[:CALLS]->(callee:Function)
    OPTIONAL MATCH (file:CodeFile)-[:DEFINES]->(target)
    OPTIONAL MATCH (file)-[:DEFINES]->(sibling) WHERE sibling <> target
    
    // Expanded relationships
    OPTIONAL MATCH (importer:CodeFile)-[:IMPORTS]->(target)
    OPTIONAL MATCH (target)-[:IMPORTS]->(imported:Code)
    OPTIONAL MATCH (target)-[:IMPORTS]->(imported_lib:Library)
    OPTIONAL MATCH (child:Class)-[:INHERITS_FROM]->(target)
    OPTIONAL MATCH (target)-[:INHERITS_FROM]->(parent:Class)
    OPTIONAL MATCH (user:Function)-[:USES_TYPE]->(target)
    
    RETURN
        target.path as path,
        collect(DISTINCT caller { .fqn, .name, .path }) AS callers,
        collect(DISTINCT callee { .fqn, .name, .path }) AS callees,
        collect(DISTINCT sibling { .fqn, .name, .path }) AS siblings,
        collect(DISTINCT importer { .fqn, .name, .path }) AS imported_by,
        collect(DISTINCT imported { .fqn, .name, .path }) AS imports_modules,
        collect(DISTINCT imported_lib { .name }) AS imports_libraries,
        collect(DISTINCT child { .fqn, .name, .path }) AS child_classes,
        collect(DISTINCT parent { .fqn, .name, .path }) AS parent_classes,
        collect(DISTINCT user { .fqn, .name, .path }) AS used_by_functions
    """
    result = await cypher_query(query, {"fqn": fqn})
    return result[0] if result else {}

async def _get_test_coverage(path: str) -> list[dict]:
    """Heuristic to find test files that import the target's module."""
    if not path:
        return []
    query = """
    MATCH (test_file:CodeFile)-[:IMPORTS*1..2]->(target_file:CodeFile {path: $path})
    WHERE test_file.path CONTAINS 'tests/'
    RETURN DISTINCT test_file { .fqn, .path }
    LIMIT 10
    """
    return await cypher_query(query, {"path": path})

async def get_multi_modal_dossier(target_fqn: str, intent: str, top_k_semantic: int = 5) -> dict[str, Any]:
    """
    Builds a god-level, comprehensive dossier for a given code entity,
    including semantic, structural, historical, and architectural context.
    """
    entry_node_data = await _get_entry_node(target_fqn)
    if not entry_node_data:
        return {"error": f"Target FQN not found in Code Graph: {target_fqn}"}

    entry_node = entry_node_data.get('n', {})
    embedding = entry_node.get("embedding")
    
    # 1. Get semantic neighbors (if we have an embedding)
    semantic_neighbors = []
    if embedding:
        semantic_neighbors = await _get_semantic_neighbors(embedding, top_k_semantic)
        
    # 2. Get structural neighbors (callers, callees, imports, etc.)
    structural_neighbors = await _get_structural_neighbors(target_fqn)
    
    # 3. Get related tests
    target_path = entry_node.get("path", "")
    related_tests = await _get_test_coverage(target_path)

    # 4. Get Multi-Modal Historical & Architectural Context
    multi_modal_query = """
    MATCH (target:Code {fqn: $fqn})
    // Find related conflicts and their solutions
    OPTIONAL MATCH (conflict:Conflict)-[:RELATES_TO]->(target)
    OPTIONAL MATCH (conflict)-[:RESOLVED_BY]->(solution:Solution)
    // Find related deliberations
    OPTIONAL MATCH (deliberation:Deliberation)-[:DISCUSSES]->(target)
    // Find related architectural decisions
    OPTIONAL MATCH (adr:ArchitecturalDecision)-[:DOCUMENTS]->(target)
    RETURN
        collect(DISTINCT conflict { .description, .context.goal, solution_diff: solution.diff }) AS related_conflicts,
        collect(DISTINCT deliberation { .deliberation_id, .summary, .verdict }) AS related_deliberations,
        collect(DISTINCT adr { .path, .title, .status }) AS related_adrs
    """
    multi_modal_context = (await cypher_query(multi_modal_query, {"fqn": target_fqn}))[0] or {}

    # 5. Construct the final dossier
    return {
        "target": {
            "fqn": entry_node.get("fqn"),
            "path": entry_node.get("path"),
            "source_code": entry_node.get("source_code"),
            "docstring": entry_node.get("docstring"),
        },
        "intent": intent,
        "analysis": {
            "semantic_neighbors": semantic_neighbors,
            "structural_neighbors": structural_neighbors,
            "related_tests": related_tests,
            "historical_context": {
                "conflicts_and_solutions": multi_modal_context.get("related_conflicts", []),
                "deliberations": multi_modal_context.get("related_deliberations", []),
            },
            "architectural_context": {
                "decision_records": multi_modal_context.get("related_adrs", [])
            }
        },
        "summary": (
            f"Dossier for '{target_fqn}'. Found {len(semantic_neighbors)} similar code items, "
            f"{len(multi_modal_context.get('related_conflicts', []))} related past conflicts, and "
            f"{len(multi_modal_context.get('related_adrs', []))} architectural records."
        ),
    }

# --- FIX: Provide a backward-compatible alias for older import statements ---
get_dossier = get_multi_modal_dossier