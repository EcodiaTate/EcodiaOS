# core/prompting/lenses.py
from __future__ import annotations

from typing import Any

# Optional imports that exist in EOS; safe fallbacks provided:
try:
    from core.utils.neo.cypher_query import cypher_query  # graph access
except Exception:
    cypher_query = None

try:
    from systems.synk.core.tools.neo import semantic_graph_search  # retrieval
except Exception:
    semantic_graph_search = None

async def lens_equor_identity(agent_name: str) -> dict[str, Any]:
    """
    Minimal identity pull: summary, purpose, facets.
    """
    if cypher_query is None:
        return {"agent_name": agent_name}

    q = """
    MATCH (a:Agent {name: $name})
    OPTIONAL MATCH (a)-[:HAS_FACET]->(f:Facet)
    RETURN a.summary AS summary, a.purpose AS purpose, collect(f.name) AS facets
    """
    rows = await cypher_query(q, {"name": agent_name})
    if not rows:
        return {"agent_name": agent_name}

    r = rows[0]
    parts = []
    if r.get("summary"):
        parts.append(str(r["summary"]).strip())
    if r.get("purpose"):
        parts.append(f"Purpose: {str(r['purpose']).strip()}")
    if r.get("facets"):
        parts.append("Facets: " + ", ".join([str(x) for x in r["facets"] if x]))
    return {
        "agent_name": agent_name,
        "identity_text": "\n".join(parts),
        "facets": r.get("facets") or [],
    }


async def lens_atune_salience(salience: dict[str, Any] | None) -> dict[str, Any]:
    return {"salience": salience or {}}


async def lens_affect(affect: dict[str, Any] | None) -> dict[str, Any]:
    # e.g., {"curiosity": 0.6, "caution": 0.2, "fatigue": 0.1}
    return {"affect": affect or {}}


async def lens_event_canonical(event: dict[str, Any] | None) -> dict[str, Any]:
    return {"event": event or {}}


async def lens_retrieval_semantic(query: str, limit: int = 6) -> dict[str, Any]:
    if not semantic_graph_search:
        return {"retrieval": []}
    items = await semantic_graph_search(query_text=query, top_k=limit)
    return {"retrieval": items or []}


# Budget-aware limiters
def cap_list(items: list[Any], max_items: int) -> list[Any]:
    return items[:max_items] if max_items >= 0 else items


def cap_chars(text: str, max_chars: int) -> str:
    return text[:max_chars] if max_chars >= 0 else text


def estimate_tokens(text: str) -> int:
    # Rough universal estimator: ~4 chars/token (safe-ish)
    return max(1, len(text) // 4)
