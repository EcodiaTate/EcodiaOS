from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

VECTOR_DIM = 3072
EMBED_MODEL = "gemini-3072"
LABEL = "Origin"  # hard lock


# -------------------------
# Indexes / constraints (driverless)
# -------------------------
async def ensure_origin_indices() -> None:
    cyphers = [
        f"CREATE CONSTRAINT origin_event_id IF NOT EXISTS FOR (n:{LABEL}) REQUIRE n.event_id IS UNIQUE",
        f"CREATE CONSTRAINT origin_uuid IF NOT EXISTS FOR (n:{LABEL}) REQUIRE n.uuid IS UNIQUE",
        (
            f"CREATE VECTOR INDEX origin_embedding IF NOT EXISTS "
            f"FOR (n:{LABEL}) ON (n.embedding) "
            f"OPTIONS {{ indexConfig: {{ `vector.dimensions`: {VECTOR_DIM}, `vector.similarity_function`: 'cosine' }} }}"
        ),
        (
            f"CREATE FULLTEXT INDEX origin_fts IF NOT EXISTS "
            f"FOR (n:{LABEL}) ON EACH [n.title, n.summary, n.what, n.where]"
        ),
    ]
    for q in cyphers:
        await cypher_query(q)


# -------------------------
# Low-level helpers (driverless)
# -------------------------
async def _embed_for_node(title: str, summary: str, what: str) -> list[float]:
    text = "\n\n".join([p for p in [title, summary, what] if p])
    return await get_embedding(text, dimensions=VECTOR_DIM)


async def _embed_for_edge(from_title: str, rel_label: str, to_title: str, note: str) -> list[float]:
    base = f"{from_title} {rel_label} {to_title}"
    if note:
        base += f" :: {note}"
    return await get_embedding(base, dimensions=VECTOR_DIM)


async def _has_origin_label(iid: int) -> bool:
    q = f"MATCH (n:{LABEL}) WHERE id(n) = $id RETURN 1 AS ok"
    rows = await cypher_query(q, {"id": iid}) or []
    return bool(rows)


async def force_origin_label(node_id: int) -> None:
    q = "MATCH (n) WHERE id(n) = $id SET n:Origin RETURN id(n) AS id"
    await cypher_query(q, {"id": node_id})


async def _title_by_id(iid: int) -> str:
    q = "MATCH (n) WHERE id(n) = $id RETURN coalesce(n.title,'') AS title"
    rows = await cypher_query(q, {"id": iid}) or []
    return (rows[0]["title"] if rows else "") or ""


# -------------------------
# Create node (always :Origin)
# -------------------------
async def create_origin_node(
    contributor: str,
    title: str,
    summary: str,
    what: str,
    where: str | None,
    when: str | None,
    tags: list[str],
) -> tuple[str, int]:
    event_id = str(uuid4())
    uuid_val = str(uuid4())
    embedding = await _embed_for_node(title, summary, what)

    q = f"""
    CREATE (n:{LABEL} {{
      event_id: $event_id,
      uuid: $uuid,
      contributor: $contributor,
      title: $title,
      summary: $summary,
      what: $what,
      where: $where,
      when: $when,
      tags: $tags,
      created_at: datetime($now),
      embedding: $embedding
    }})
    RETURN id(n) as id
    """
    params = {
        "event_id": event_id,
        "uuid": uuid_val,
        "contributor": contributor,
        "title": title,
        "summary": summary,
        "what": what,
        "where": where,
        "when": when,
        "tags": tags,
        "now": datetime.utcnow().isoformat(),
        "embedding": embedding,
    }
    rows = await cypher_query(q, params) or []
    node_id = rows[0]["id"]

    # Defensive: ensure Origin label even if LABEL changes upstream
    await force_origin_label(node_id)
    return event_id, node_id


# -------------------------
# Resolve IDs (Origin only)
# -------------------------
async def resolve_event_or_internal_id(any_id: str) -> int:
    if any_id.isdigit():
        iid = int(any_id)
        if not await _has_origin_label(iid):
            raise ValueError(f"Node {iid} is not labeled :{LABEL}")
        return iid

    q = f"MATCH (n:{LABEL} {{event_id:$eid}}) RETURN id(n) AS id"
    rows = await cypher_query(q, {"eid": any_id}) or []
    if not rows:
        raise ValueError(f"{LABEL} node not found for event_id={any_id}")
    return rows[0]["id"]


# -------------------------
# Edge creation (driverless)
# -------------------------
async def create_edges_from(from_internal_id: int, edges: list[dict[str, Any]]) -> int:
    """
    edges: [{to_id, label, note}]
    Adds relationship embedding.
    from_internal_id must be :Origin.
    """
    if not await _has_origin_label(from_internal_id):
        raise ValueError(f"from_internal_id {from_internal_id} is not an :{LABEL} node")

    created = 0
    from_title = await _title_by_id(from_internal_id)

    for e in edges:
        to_id_any = e.get("to_id")
        if to_id_any is None:
            continue

        to_id: int | None = None

        # Resolve by numeric internal id
        if str(to_id_any).isdigit():
            to_id = int(to_id_any)
        else:
            # Try event_id
            rows = (
                await cypher_query(
                    "MATCH (n {event_id:$eid}) RETURN id(n) AS id",
                    {"eid": to_id_any},
                )
                or []
            )
            if rows:
                to_id = rows[0]["id"]

        # Try uuid if still not found
        if to_id is None:
            rows = (
                await cypher_query("MATCH (n {uuid:$u}) RETURN id(n) AS id", {"u": to_id_any}) or []
            )
            if rows:
                to_id = rows[0]["id"]

        if to_id is None:
            continue

        to_title = await _title_by_id(to_id)
        rel_label = (e.get("label") or "").strip().upper().replace(" ", "_")
        if not rel_label:
            continue
        note = e.get("note") or ""
        emb = await _embed_for_edge(from_title, rel_label, to_title, note)

        q = """
        MATCH (a) WHERE id(a) = $a_id
        MATCH (b) WHERE id(b) = $b_id
        CALL apoc.create.relationship(
          a, $rtype,
          { note:$note, embedding:$emb, created_at: datetime($now) },
          b
        ) YIELD rel
        RETURN id(rel) AS rid
        """
        rows = (
            await cypher_query(
                q,
                {
                    "a_id": from_internal_id,
                    "b_id": to_id,
                    "rtype": rel_label,
                    "note": note,
                    "emb": emb,
                    "now": datetime.utcnow().isoformat(),
                },
            )
            or []
        )
        if rows:
            created += 1

    return created


# -------------------------
# Search (Origin-only; driverless)
# -------------------------
async def search_mixed(query: str, k: int = 10) -> list[dict[str, Any]]:
    q_fts = """
    CALL db.index.fulltext.queryNodes('origin_fts', $q) YIELD node, score
    RETURN id(node) AS id, labels(node) AS labels, node.title AS title, node.summary AS summary, score
    LIMIT $lim
    """
    emb = await get_embedding(query, dimensions=VECTOR_DIM)
    q_vec = """
    CALL db.index.vector.queryNodes('origin_embedding', $lim, $qvec)
    YIELD node, score
    RETURN id(node) AS id, labels(node) AS labels, node.title AS title, node.summary AS summary, score
    """

    lim = max(k, 10)
    rows_by_id: dict[int, dict[str, Any]] = {}

    fts_rows = await cypher_query(q_fts, {"q": query, "lim": lim * 2}) or []
    for r in fts_rows:
        rows_by_id[r["id"]] = {
            "id": str(r["id"]),
            "labels": r["labels"],
            "title": r.get("title"),
            "summary": r.get("summary"),
            "score": float(r.get("score") or 0.0),
        }

    vec_rows = await cypher_query(q_vec, {"qvec": emb, "lim": lim * 2}) or []
    for r in vec_rows:
        rid = r["id"]
        sscore = float(r.get("score") or 0.0)
        if rid in rows_by_id:
            rows_by_id[rid]["score"] = max(rows_by_id[rid]["score"], sscore)
        else:
            rows_by_id[rid] = {
                "id": str(rid),
                "labels": r["labels"],
                "title": r.get("title"),
                "summary": r.get("summary"),
                "score": sscore,
            }

    return sorted(rows_by_id.values(), key=lambda x: x.get("score") or 0.0, reverse=True)[:k]
