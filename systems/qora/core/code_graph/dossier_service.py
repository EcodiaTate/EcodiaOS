# systems/qora/core/code_graph/dossier_service.py
# --- GOD-LEVEL UPGRADE (FINAL, :Code-first compatible) ---
from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query

# --------------------------- Entry Resolution ---------------------------


async def _get_entry_node(fqn: str) -> dict | None:
    """
    Resolve the target :Code node. We return a plain dict via n{.*} so callers
    don't have to deal with Node objects. Matching tolerates dotted vs canonical FQN.
    """
    q = (fqn or "").strip()
    if not q:
        return None

    leaf = q.split("::")[-1].split(".")[-1]

    # Pass 1: exact match on fqn / qualname / name
    query_exact = """
    WITH $q AS q
    MATCH (n:Code)
    WHERE coalesce(toString(n['fqn']), '') = q
       OR coalesce(toString(n['qualname']), '') = q
       OR coalesce(toString(n['name']), '') = q
    RETURN n{ .* } AS n
    LIMIT 1
    """
    rows = await cypher_query(query_exact, {"q": q})
    if rows:
        return rows[0]

    # Pass 2: suffix match for the symbol leaf
    query_suffix = """
    WITH $leaf AS leaf
    MATCH (n:Code)
    WHERE coalesce(toString(n['fqn']), '')      ENDS WITH '.'  + leaf
       OR coalesce(toString(n['fqn']), '')      ENDS WITH '::' + leaf
       OR coalesce(toString(n['qualname']), '') ENDS WITH '.'  + leaf
       OR coalesce(toString(n['name']), '') = leaf
    RETURN n{ .* } AS n
    LIMIT 1
    """
    rows = await cypher_query(query_suffix, {"leaf": leaf})
    if rows:
        return rows[0]

    # Pass 3: light contains probe (only if leaf is not tiny)
    if len(leaf) >= 4:
        query_contains = """
        WITH $leaf AS leaf
        MATCH (n:Code)
        WHERE toLower(coalesce(toString(n['fqn']), ''))      CONTAINS toLower(leaf)
           OR toLower(coalesce(toString(n['qualname']), '')) CONTAINS toLower(leaf)
        RETURN n{ .* } AS n
        LIMIT 1
        """
        rows = await cypher_query(query_contains, {"leaf": leaf})
        if rows:
            return rows[0]

    return None


# --------------------------- Semantic Neighbors ---------------------------


async def _get_semantic_neighbors(embedding: list[float], top_k: int) -> list[dict]:
    """Find semantically similar code using the vector index."""
    query = """
    CALL db.index.vector.queryNodes('code_embedding', $top_k, $embedding)
    YIELD node, score
    RETURN
        node.fqn  AS fqn,
        node.name AS name,
        node.path AS path,
        left(node.docstring, 200) AS docstring,
        score
    """
    return await cypher_query(query, {"top_k": top_k, "embedding": embedding})


# --------------------------- Structural Neighbors ---------------------------


async def _get_structural_neighbors(canonical_fqn: str) -> dict:
    """
    Structural neighbors with conservative Cypher:
    - Use generic relationship variables and filter by type() to avoid
      UnknownRelationshipType warnings if some rel types are absent.
    - Group & dedupe in Python for cleanliness.
    """
    query = """
    // Structural neighbors for a Code FQN (schema: CodeFile -[:DEFINES]-> Code)
    MATCH (t:Code {fqn:$fqn})

    OPTIONAL MATCH (f:CodeFile)-[:DEFINES]->(t)
    WITH t, f

    // outgoing structural edges among Code (generic rel + type() filter)
    OPTIONAL MATCH (t)-[r_out]->(o:Code)
    WHERE type(r_out) IN ['CALLS','USES_TYPE','INHERITS_FROM','REFS','USES']
    WITH t, f, collect({rel:type(r_out), fqn:o.fqn, name:o.name, path:o.path}) AS outgoing_pairs

    // incoming structural edges among Code
    OPTIONAL MATCH (t)<-[r_in]-(i:Code)
    WHERE type(r_in) IN ['CALLS','USES_TYPE','INHERITS_FROM','REFS','USES']
    WITH t, f, outgoing_pairs, collect({rel:type(r_in), fqn:i.fqn, name:i.name, path:i.path}) AS incoming_pairs

    // siblings = other symbols defined by the same file
    OPTIONAL MATCH (f)-[:DEFINES]->(sib:Code)
    WHERE sib <> t
    WITH t, f, outgoing_pairs, incoming_pairs, collect({fqn:sib.fqn, name:sib.name, path:sib.path}) AS sibs

    RETURN
      coalesce(t.path,'') AS path,
      CASE WHEN f IS NULL THEN NULL ELSE f { .path, .module } END AS container,
      outgoing_pairs,
      incoming_pairs,
      sibs
    """
    rows = await cypher_query(query, {"fqn": canonical_fqn})
    if not rows:
        return {}

    rec = rows[0]

    def _node_view(n: dict | None) -> dict | None:
        if not n:
            return None
        return {"fqn": n.get("fqn"), "name": n.get("name"), "path": n.get("path")}

    def _dedupe(nodes: list[dict]) -> list[dict]:
        seen: set[tuple] = set()
        out: list[dict] = []
        for v in nodes or []:
            key = (v.get("fqn"), v.get("name"), v.get("path"))
            if key not in seen:
                seen.add(key)
                out.append(v)
        return out

    def _group_pairs(pairs: list[dict] | None) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for p in pairs or []:
            rel = p.get("rel")
            if not rel:
                continue
            view = _node_view(p)
            if not view:
                continue
            grouped.setdefault(rel, []).append(view)
        for rel, lst in grouped.items():
            grouped[rel] = _dedupe(lst)
        return grouped

    outgoing = _group_pairs(rec.get("outgoing_pairs"))
    incoming = _group_pairs(rec.get("incoming_pairs"))

    def _collect(src: dict[str, list[dict]], names: list[str]) -> list[dict]:
        acc: list[dict] = []
        for nm in names:
            acc.extend(src.get(nm, []))
        return _dedupe(acc)

    # Be flexible: if the graph doesn’t use a specific rel name, just collect what exists.
    callees = _collect(outgoing, list(outgoing.keys()))
    callers = _collect(incoming, list(incoming.keys()))

    siblings = _dedupe([_node_view(s) for s in (rec.get("sibs") or []) if _node_view(s)])
    container_view = _node_view(rec.get("container")) if rec.get("container") else None

    return {
        "path": rec.get("path"),
        "container": container_view,
        "siblings": siblings,
        "callers": callers,
        "callees": callees,
        "imported_by": [],  # CodeFile IMPORTS live on files, not symbols
        "imports_modules": [],
        "raw_by_rel": {"outgoing": outgoing, "incoming": incoming},
    }


# --------------------------- Test Coverage ---------------------------


async def _get_test_coverage(path: str) -> list[dict]:
    """
    Find test files importing the target file (CodeFile → IMPORTS).
    """
    if not path:
        return []
    query = """
    WITH toLower($path) AS p
    MATCH (target_file:CodeFile)
    WHERE toLower(target_file.path) = p

    MATCH (test_file:CodeFile)-[:IMPORTS*1..2]->(target_file)
    WHERE toLower(test_file.path) CONTAINS '/tests/'
       OR toLower(test_file.path) STARTS WITH 'tests/'

    OPTIONAL MATCH (test_file)-[:DEFINES]->(ts:Code)
    RETURN DISTINCT
      test_file.path AS test_path,
      collect(DISTINCT {fqn: ts.fqn, name: ts.name}) AS test_symbols
    LIMIT 10
    """
    return await cypher_query(query, {"path": path})


# --------------------------- Public Builder ---------------------------


async def get_multi_modal_dossier(
    target_fqn: str,
    intent: str,
    top_k_semantic: int = 5,
) -> dict[str, Any]:
    """
    Build a comprehensive dossier for a given code entity.
    Key fix: after resolving the node, use its **canonical FQN** everywhere.
    """
    entry_node_data = await _get_entry_node(target_fqn)
    if not entry_node_data:
        return {"error": f"Target FQN not found in Code Graph: {target_fqn}"}

    entry_node = entry_node_data.get("n", {}) or {}
    canonical_fqn = entry_node.get("fqn") or entry_node.get("qualname") or entry_node.get("name")
    target_path = (
        entry_node.get("path") or entry_node.get("filepath") or entry_node.get("relpath") or ""
    )

    # 1) Semantic neighbors
    semantic_neighbors: list[dict] = []
    embedding = entry_node.get("embedding")
    if embedding:
        raw_hits = await _get_semantic_neighbors(embedding, top_k_semantic)
        semantic_neighbors = [h for h in raw_hits if h.get("fqn") != canonical_fqn]

    # 2) Structural neighbors (now using canonical FQN)
    structural_neighbors = await _get_structural_neighbors(canonical_fqn)

    # 3) Related tests
    related_tests = await _get_test_coverage(target_path)

    # 4) Historical / ADR context (also using canonical FQN)
    multi_modal_query = """
    WITH $fqn AS f
    MATCH (target:Code {fqn: f})

    // Conflicts (avoid UnknownRelationshipType by matching generic rels)
    OPTIONAL MATCH (conflict)-[r1]->(target)
    WHERE 'Conflict' IN labels(conflict) AND type(r1) = 'RELATES_TO'

    // Deliberations
    OPTIONAL MATCH (delib)-[r3]->(target)
    WHERE 'Deliberation' IN labels(delib) AND type(r3) = 'DISCUSSES'

    // Architectural decisions
    OPTIONAL MATCH (adr)-[r4]->(target)
    WHERE 'ArchitecturalDecision' IN labels(adr) AND type(r4) = 'DOCUMENTS'

    RETURN
      collect(DISTINCT {
        description: conflict['description'],
        context:     conflict['last_context_json']
      }) AS related_conflicts,
      collect(DISTINCT {
        deliberation_id: delib['deliberation_id'],
        summary:         delib['summary']
      }) AS related_deliberations,
      collect(DISTINCT {
        path:   adr['path'],
        title:  adr['title'],
        status: adr['status']
      }) AS related_adrs
      """
    mm_rows = await cypher_query(multi_modal_query, {"fqn": canonical_fqn})
    multi_modal_context = (mm_rows[0] if mm_rows else {}) or {}

    return {
        "target": {
            "fqn": canonical_fqn,
            "path": target_path,
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
                "decision_records": multi_modal_context.get("related_adrs", []),
            },
        },
        "summary": (
            f"Dossier for '{canonical_fqn}'. Found {len(semantic_neighbors)} similar code items, "
            f"{len(multi_modal_context.get('related_conflicts', []))} related past conflicts, and "
            f"{len(multi_modal_context.get('related_adrs', []))} architectural records."
        ),
    }


# Back-compat alias
get_dossier = get_multi_modal_dossier
