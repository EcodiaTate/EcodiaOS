# systems/synk/core/tools/neo.py

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable, Sequence
from typing import Any
from uuid import uuid4

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, get_http_client

# EcodiaOS Core Imports
from core.utils.time import now_iso

from .vector_store import embed_and_add_node_vector  # search_vector_index if/when needed

# =========================
# 헬퍼 Helpers (Internal)
# =========================


def _safe_neo_props(props: dict[str, Any]) -> dict[str, Any]:
    """Prepares a dictionary for safe insertion as Neo4j properties."""

    def _safe(val):
        if isinstance(val, dict | list):
            return json.dumps(val, separators=(",", ":"))
        return val

    return {k: _safe(v) for k, v in (props or {}).items()}


def _get_or_make_event_id(properties: dict[str, Any]) -> str:
    """Ensures an event_id exists in a properties dictionary."""
    event_id = properties.get("event_id") or str(uuid.uuid4())
    properties["event_id"] = event_id
    return event_id


# =========================
# 엣지 Edges
# =========================


# Likely located in: systems/synk/core/tools/neo.py

# Likely located in: systems/synk/core/tools/neo.py

from typing import Any

from core.utils.neo.cypher_query import cypher_query

# In systems/synk/core/tools/neo.py


async def add_relationship(
    src_match: dict[str, Any],
    dst_match: dict[str, Any],
    rel_type: str,
    *,
    rel_props: dict[str, Any] | None = None,
):
    """
    Creates a relationship between two nodes using an efficient, non-cartesian product query.
    """
    src_label = src_match.get("label", "")
    dst_label = dst_match.get("label", "")

    if not src_label or not dst_label or not src_match.get("match") or not dst_match.get("match"):
        raise ValueError(
            "add_relationship requires a label and a match property for both source and destination."
        )

    src_key = list(src_match["match"].keys())[0]
    dst_key = list(dst_match["match"].keys())[0]
    src_val = src_match["match"][src_key]
    dst_val = dst_match["match"][dst_key]

    # --- THIS IS THE CORRECTED QUERY ---
    # It uses parameter substitution for VALUES ONLY, which is the correct and safe way.
    query = f"""
    MATCH (a:{src_label} {{ {src_key}: $src_val }})
    MATCH (b:{dst_label} {{ {dst_key}: $dst_val }})
    MERGE (a)-[r:{rel_type}]->(b)
    ON CREATE SET r = $rel_props
    ON MATCH SET r += $rel_props
    """

    params = {
        "src_val": src_val,
        "dst_val": dst_val,
        "rel_props": rel_props or {},
    }
    await cypher_query(query, params)


# =========================
# 벡처/시맨틱 검색 Vector/Semantic Search
# =========================

INDEX_MAP = {
    "Event": "gemini-3072-index",
    "Cluster": "cluster_cluster_vector_gemini_3072_cosine",
    "SoulNode": "soulnode-3072-index",
}


def _ensure_list(v: Any) -> list[float] | None:
    """
    Coerce various persisted/vector formats into List[float].
    Accepts list/tuple, JSON-encoded string, or returns None.
    """
    if v is None:
        return None
    if isinstance(v, list | tuple):
        try:
            return [float(x) for x in v]
        except Exception:
            return None
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list | tuple):
                return [float(x) for x in parsed]
        except Exception:
            return None
    return None


async def fetch_exemplar_embeddings(
    scorer: str,
    limit: int = 50,
    *,
    prefer: str = "gemini",  # "gemini" | "openai" | "any"
    reembed_missing_gemini: bool = True,  # on-the-fly only; does not persist
) -> list[dict[str, Any]]:
    """
    Fetch exemplar vectors for a given scorer from :SemanticExemplar.
    Returns 3072-dim vectors when available (or on-the-fly via Gemini if allowed).

    Driverless: uses core.utils.neo.cypher_query.cypher_query
    """
    prefer_l = (prefer or "any").lower()
    if prefer_l not in {"gemini", "openai", "any"}:
        prefer_l = "any"

    q = """
    MATCH (e:SemanticExemplar)
    WHERE toLower(e.scorer) = toLower($scorer)
    RETURN
      e.uuid                AS uuid,
      e.text                AS text,
      e.vector_gemini       AS v_gemini,
      e.vector_openai_1536  AS v_oai
    LIMIT $limit
    """
    rows = await cypher_query(q, {"scorer": scorer, "limit": int(limit)})

    out: list[dict[str, Any]] = []
    for r in rows or []:
        text = (r.get("text") or "").strip()
        uuid_val = r.get("uuid") or str(uuid.uuid4())
        v_gemini = _ensure_list(r.get("v_gemini"))
        v_oai = _ensure_list(r.get("v_oai"))

        embedding: list[float] | None = None

        if prefer_l == "gemini":
            embedding = v_gemini
            if embedding is None and reembed_missing_gemini and text:
                try:
                    embedding = _ensure_list(await get_embedding(text))
                except Exception:
                    embedding = None

        elif prefer_l == "openai":
            embedding = v_oai
            if embedding is None and v_gemini is not None:
                embedding = v_gemini
            elif embedding is None and reembed_missing_gemini and text:
                # still allow on-the-fly gemini as a last resort
                try:
                    embedding = _ensure_list(await get_embedding(text))
                except Exception:
                    embedding = None

        else:  # "any"
            embedding = v_gemini or v_oai
            if embedding is None and reembed_missing_gemini and text:
                try:
                    embedding = _ensure_list(await get_embedding(text))
                except Exception:
                    embedding = None

        if embedding is None:
            continue

        out.append({"text": text, "uuid": uuid_val, "embedding": embedding})

    return out


async def semantic_graph_search(
    query_text: str,
    top_k: int = 5,
    labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    High-performance ANN over Neo4j 5 vector indexes.
    DRIVERLESS: does not require a `driver` argument.
    """
    if not query_text or not query_text.strip():
        return []

    vec = await get_embedding(query_text)
    index_names = [INDEX_MAP.get(l, INDEX_MAP["Event"]) for l in (labels or ["Event"])]

    query = """
    CALL db.index.vector.queryNodes($index, $k, $vec)
    YIELD node AS n, score
    RETURN score, labels(n) AS labels, n { .*, vector_gemini: null } AS props
    ORDER BY score DESC LIMIT $k
    """

    all_results: list[dict[str, Any]] = []
    for index_name in set(index_names):
        rows = await cypher_query(
            query,
            {"index": index_name, "k": int(top_k), "vec": vec},
        )
        for r in rows or []:
            all_results.append(
                {
                    "n": r.get("props") or {},
                    "labels": r.get("labels") or [],
                    "score": float(r.get("score", 0.0)),
                },
            )

    # De-duplicate across multiple index searches
    seen = set()
    deduped = []
    for item in sorted(all_results, key=lambda x: x["score"], reverse=True):
        props = item["n"]
        key = props.get("event_id") or props.get("uuid")
        if key and key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped[: int(top_k)]


# =========================
# 노드 Nodes
# =========================

_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


async def add_node(
    labels: Sequence[str] | str,
    properties: dict[str, Any] | None = None,
    embed_text: str | None = None,
) -> dict[str, Any]:
    """
    Public-facing function to create or merge a node.
    Accepts labels as a list or a single string.
    """
    # --- NEW: coerce labels ---
    if isinstance(labels, str):
        labels_list = [labels]
    else:
        labels_list = list(labels)

    # Optional: sanitize/validate labels to avoid spaces, invalid chars
    clean_labels: list[str] = []
    for lab in labels_list:
        lab = lab.strip().replace(" ", "")  # 'Prompt Patch' -> 'PromptPatch'
        if not lab:
            continue
        if not _LABEL_RE.match(lab):
            # If you want to be strict, raise instead:
            # raise ValueError(f"Invalid Neo4j label: {lab!r}")
            # Or soften by stripping non-alnum/underscore:
            lab = re.sub(r"[^A-Za-z0-9_]", "", lab)
            if not lab or not _LABEL_RE.match(lab):
                raise ValueError(f"Invalid Neo4j label after cleanup: {lab!r}")
        clean_labels.append(lab)

    if not clean_labels:
        raise ValueError("At least one valid label is required.")

    label_str = ":" + ":".join(clean_labels)

    props = dict(properties) if properties else {}
    event_id = _get_or_make_event_id(props)  # assuming this sets props["event_id"] internally
    props.setdefault("uuid", event_id)

    if "fqn" in props and "hash" in props:
        merge_keys = ["fqn", "hash"]
    elif "name" in props and "system" in props:
        merge_keys = ["name", "system"]
    else:
        merge_keys = ["event_id"]

    merge_condition = ", ".join(f"{k}: $props.{k}" for k in merge_keys)
    set_clause = "ON CREATE SET n = $props, n.created_at = datetime() ON MATCH SET n += $props"

    query = (
        f"MERGE (n{label_str} {{ {merge_condition} }}) {set_clause} RETURN n, labels(n) AS n_labels"
    )
    results = await cypher_query(query, {"props": _safe_neo_props(props)})

    if embed_text:
        await embed_and_add_node_vector(text=embed_text, node_id=event_id, id_property="event_id")

    if results:
        record = results[0]
        node_props = dict(record.get("n"))
        return {
            "event_id": node_props.get("event_id"),
            "uuid": node_props.get("uuid"),
            "labels": record.get("n_labels", []),
            "properties": node_props,
        }
    raise ValueError("Node creation failed to return a result.")


from hashlib import sha256

from core.utils.net_api import ENDPOINTS, post_internal

# systems/common/conflicts/store.py  (drop-in replacement for create_conflict_node)
IDEMPOTENCY_TTL_SEC = 300  # 5 min; tune


def _stable_cid(system: str, origin_node_id: str, description: str, modules: list[str]) -> str:
    # Normalize description to avoid whitespace/case churn
    d = " ".join((description or "").split()).lower()
    key = f"{system}|{origin_node_id}|{d}|{','.join(sorted(modules))}"
    return sha256(key.encode("utf-8")).hexdigest()[:32]


async def _ttl_gate(cid: str) -> bool:
    """
    Returns True if we should proceed (not seen recently).
    Neo4j fallback: MERGE a key and check age; skip if too fresh.
    """
    q = """
    MERGE (k:EscalationKey {id:$id})
    ON CREATE SET k.created_at = datetime()
    WITH k, duration.between(k.created_at, datetime()) AS age
    RETURN (age.seconds IS NULL OR age.seconds >= $ttl) AS allow
    """
    try:
        rows = await cypher_query(q, {"id": cid, "ttl": IDEMPOTENCY_TTL_SEC}) or []
        return bool(rows and rows[0].get("allow"))
    except Exception:
        # If graph is down, allow once to avoid blocking
        return True


async def create_conflict_node(
    system: str,
    description: str,
    origin_node_id: str,
    additional_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = additional_data or {}

    # --- embedding (best-effort) ---
    try:
        embed_text = data.get("goal", description)
        embedding = await get_embedding(embed_text, task_type="RETRIEVAL_DOCUMENT")
    except Exception:
        embedding = []

    modules = data.get("modules")
    if not isinstance(modules, list):
        modules = [data["module"]] if "module" in data else []

    # >>> deterministic conflict id <<<
    conflict_cid = _stable_cid(system, origin_node_id, description, modules)

    conflict_props = {
        "conflict_id": conflict_cid,
        "system": system,
        "source_system": system,
        "description": description,
        "origin_node_id": origin_node_id,
        "summary": data.get("summary") or description,
        "severity": (data.get("severity") or "medium").lower(),
        "tags": data.get("tags", []),
        "status": "open",
        "created_at": now_iso(),
        "embedding": embedding or [],
        "modules": modules,
        "context": data,
    }

    from systems.synk.core.tools.neo import add_node

    conflict_node = await add_node(labels=["Conflict"], properties=conflict_props)

    # >>> short TTL idempotency before notifying Evo <<<
    if not await _ttl_gate(conflict_cid):
        print(f"[Synk] ⏭️  Skipping duplicate escalate for conflict {conflict_cid} (TTL gate).")
        return conflict_node

    # notify Evo patrol (immune internal call)
    try:
        evo_payload = {
            "conflict_id": conflict_cid,
            "description": description,
            "tags": data.get("tags", []),
            "brief_overrides": data.get("brief_overrides") or {},
            "budget_ms": data.get("budget_ms"),
        }
        headers = {
            "x-ecodia-immune": "1",
            "x-decision-id": f"auto-{uuid.uuid4().hex[:8]}",
            "x-budget-ms": str(data.get("budget_ms", 4000)),
        }
        resp = await post_internal(
            ENDPOINTS.EVO_ESCALATE, json=evo_payload, headers=headers, timeout=10.0
        )
        resp.raise_for_status()
        print(f"[Synk] ✅ Evo patrol successfully notified of conflict {conflict_cid}.")
    except Exception as e:
        print(
            f"[Synk] ⚠️ WARNING: Failed to notify Evo patrol for conflict {conflict_cid}. Error: {e}"
        )

    return conflict_node
