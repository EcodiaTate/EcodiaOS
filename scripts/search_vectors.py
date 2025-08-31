# scripts/search_vectors.py  — driverless refactor
"""
Quick vector search (driverless):
- Embeds your query with the same model used in EcodiaOS
- Queries Neo4j vector index (Cluster or Event) via cypher_query(...)
- Prints top-k hits with scores and a few fields

Usage:
  python scripts/search_vectors.py --query "climate adaptation" --mode cluster --top-k 5
  python scripts/search_vectors.py -q "ai safety" -m event -k 10
"""

import argparse
import asyncio
from typing import Any

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

# ---- Config ---------------------------------------------------------------

# Default index names (must match your vector index creation)
CLUSTER_INDEX = "cluster_cluster_vector_gemini_3072_cosine"
EVENT_INDEX = "gemini-3072-index"

# Embedding dimensions used for the indexes above
EMBED_DIMS = 3072

# Fields to show for each mode
CLUSTER_FIELDS = ["cluster_key", "run_id", "cluster_id", "size", "summary"]
EVENT_FIELDS = ["event_id", "content", "summary", "cluster_id"]


# ---- Helpers --------------------------------------------------------------


async def query_vector_index(
    index_name: str,
    embedding: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    """
    Calls db.index.vector.queryNodes and returns a list of dicts like:
      [{'node': <props>, 'score': float}, ...]
    """
    q = """
    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
    YIELD node, score
    RETURN node, score
    """
    rows = await cypher_query(
        q,
        {"index_name": index_name, "top_k": int(top_k), "embedding": embedding},
    )
    return rows or []


def _prop_get(node: Any, key: str) -> Any:
    """Safely extract a property from a Neo4j node-like object or dict."""
    if isinstance(node, dict):
        return node.get(key)
    try:
        # neo4j.Node → cast to dict to access properties
        return dict(node).get(key)
    except Exception:
        return None


def format_node(node: Any, fields: list[str]) -> dict[str, Any]:
    """Extract a few fields safely from a Neo4j node."""
    return {f: _prop_get(node, f) for f in fields}


# ---- Search modes ---------------------------------------------------------


async def search_clusters(query: str, top_k: int) -> None:
    emb = await get_embedding(query, dimensions=EMBED_DIMS)
    rows = await query_vector_index(CLUSTER_INDEX, emb, top_k)
    print(f"\n# Cluster search: '{query}'  (top {top_k})")
    if not rows:
        print("No results.")
        return
    for i, r in enumerate(rows, 1):
        node = r.get("node")
        score = float(r.get("score", 0.0))
        props = format_node(node, CLUSTER_FIELDS)
        print(f"{i:>2}. score={score:.4f}  cid={props.get('cluster_id')}  size={props.get('size')}")
        summ = props.get("summary") or ""
        preview = summ[:180].replace("\n", " ")
        if preview:
            trunc = "…" if len(summ) > 180 else ""
            print(f"    run_id={props.get('run_id')}  key={props.get('cluster_key')}")
            print(f"    summary: {preview}{trunc}")


async def search_events(query: str, top_k: int) -> None:
    emb = await get_embedding(query, dimensions=EMBED_DIMS)
    rows = await query_vector_index(EVENT_INDEX, emb, top_k)
    print(f"\n# Event search: '{query}'  (top {top_k})")
    if not rows:
        print("No results.")
        return
    for i, r in enumerate(rows, 1):
        node = r.get("node")
        score = float(r.get("score", 0.0))
        props = format_node(node, EVENT_FIELDS)
        text_src = props.get("content") or props.get("summary") or ""
        preview = text_src[:180].replace("\n", " ")
        print(
            f"{i:>2}. score={score:.4f}  event_id={props.get('event_id')}  cluster_id={props.get('cluster_id')}",
        )
        if preview:
            trunc = "…" if len(text_src) > 180 else ""
            print(f"    text: {preview}{trunc}")


# ---- CLI ------------------------------------------------------------------


async def main():
    parser = argparse.ArgumentParser(description="EcodiaOS Vector Search (driverless)")
    parser.add_argument("-q", "--query", required=True, help="Search text to embed and query with")
    parser.add_argument("-k", "--top-k", type=int, default=5, help="How many results to return")
    parser.add_argument(
        "-m",
        "--mode",
        choices=["cluster", "event"],
        default="cluster",
        help="Search clusters or events",
    )
    args = parser.parse_args()

    if args.mode == "cluster":
        await search_clusters(args.query, args.top_k)
    else:
        await search_events(args.query, args.top_k)


if __name__ == "__main__":
    asyncio.run(main())
