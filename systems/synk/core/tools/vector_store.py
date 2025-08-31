"""
🧠 EcodiaOS Vector Store Manager (driverless)
- Manages Gemini embeddings and Neo4j vector indexes via cypher_query(...)
- Provides high-performance ANN search
"""

from __future__ import annotations

from typing import Any

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

DEFAULT_LABEL = "Event"
DEFAULT_PROP = "vector_gemini"
DEFAULT_DIMS = 3072
DEFAULT_SIM = "cosine"


def _index_name(label: str, prop: str, dims: int, sim: str, name: str | None = None) -> str:
    if name:
        return name
    return f"{label.lower()}_{prop.lower()}_{dims}_{sim}".replace(".", "_")


def _quote_ident(x: str) -> str:
    # Backtick-quote a Cypher identifier safely
    return f"`{(x or '').replace('`', '')}`"


async def create_vector_index(
    driver_like: Any = None,  # tolerated for tool-wrapper compatibility (ignored)
    *,
    label: str = DEFAULT_LABEL,
    prop: str = DEFAULT_PROP,
    dims: int = DEFAULT_DIMS,
    sim: str = DEFAULT_SIM,
    name: str | None = None,
    meta: dict[str, Any] | None = None,  # tolerated for API layer pass-through
) -> str:
    """
    Create a Neo4j vector index if it doesn't exist. Returns the index name.
    """
    idx = _index_name(label, prop, dims, sim, name)
    q = f"""
    CREATE VECTOR INDEX {_quote_ident(idx)} IF NOT EXISTS
    FOR (n:{_quote_ident(label)}) ON (n.{_quote_ident(prop)})
    OPTIONS {{ indexConfig: {{
        `vector.dimensions`: $dims,
        `vector.similarity_function`: $sim
    }}}}
    """
    await cypher_query(q, {"dims": int(dims), "sim": str(sim)})
    return idx


async def embed_and_add_node_vector(
    driver_like: Any = None,
    *,
    text: str,
    node_id: str,
    id_property: str = "event_id",
    prop: str = DEFAULT_PROP,
    dims: int = DEFAULT_DIMS,
    meta: dict[str, Any] | None = None,
) -> None:
    """
    Generate an embedding for 'text' and write it to node.{prop} for the node matched by id_property.
    """
    if not text or not node_id:
        return
    emb = await get_embedding(text, dimensions=int(dims))
    q = f"""
    MATCH (n {{ {_quote_ident(id_property)}: $node_id }})
    SET n.{_quote_ident(prop)} = $embedding
    """
    await cypher_query(q, {"node_id": node_id, "embedding": emb})


async def search_vector_index(
    driver_like: Any = None,
    query_text: str = "",
    top_k: int = 5,
    *,
    label: str = DEFAULT_LABEL,
    prop: str = DEFAULT_PROP,
    dims: int = DEFAULT_DIMS,
    sim: str = DEFAULT_SIM,
    index_name: str | None = None,
    ensure_index: bool = False,
    meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Perform ANN search using db.index.vector.queryNodes against the computed index.
    Returns rows like [{'node': <Node>, 'score': float}, ...].
    """
    if not query_text:
        return []

    idx = _index_name(label, prop, int(dims), str(sim), index_name)
    if ensure_index:
        await create_vector_index(label=label, prop=prop, dims=int(dims), sim=str(sim), name=idx)

    embedding = await get_embedding(query_text, dimensions=int(dims))
    q = """
    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
    YIELD node, score
    RETURN node, score
    """
    params = {"index_name": idx, "top_k": int(top_k), "embedding": embedding}
    return await cypher_query(q, params) or []
