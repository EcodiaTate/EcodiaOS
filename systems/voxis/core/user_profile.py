# systems/voxis/core/user_profile.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

# ---- Config / conventions ----------------------------------------------------

SOULINPUT_INDEX_CANDIDATES = [
    "soulinput-gemini-3072",  # new
]

SOULRESPONSE_INDEX_CANDIDATES = [
    "soulresponse-gemini-3072",
]

# Hard limit so prompts don’t explode
MAX_CONTEXT_TOKENS_HINT = 1800  # planner hint only; we clip by message count below
MAX_CONTEXT_MESSAGES = 20  # absolute guard


# ---- Turn ingestion & linking -----------------------------------------------


async def ingest_turn_node(
    *,
    role: str,  # "user" | "assistant"
    user_id: str,
    session_id: str,
    text: str,
    ts: datetime | None = None,
) -> str | None:
    """
    Creates a SoulInput (user) or SoulResponse (assistant) node with embedding.
    Returns elementId of the created node (or None on failure).
    """
    if not text or not text.strip():
        return None

    try:
        vec = await get_embedding(text, task_type="RETRIEVAL_DOCUMENT")
    except Exception:
        vec = None  # allow creation without vector if embed fails

    node_label = "SoulInput" if role == "user" else "SoulResponse"
    q = f"""
    CREATE (n:{node_label})
    SET n.uuid       = $uid,
        n.user_id    = $uid,
        n.session_id = $sid,
        n.text       = $txt,
        n.timestamp  = datetime($ts),
        n.embedding  = $vec
    RETURN elementId(n) AS id
    """
    rows = await cypher_query(
        q,
        {
            "uid": user_id,
            "sid": session_id,
            "txt": text,
            "ts": (ts or datetime.now(UTC)).isoformat(),
            "vec": vec,
        },
    )
    return rows[0]["id"] if rows else None


async def link_input_to_response(input_id: str | None, response_id: str | None) -> None:
    """
    Adds (SoulInput)-[:GENERATES]->(SoulResponse) if both ids exist.
    """
    if not input_id or not response_id:
        return
    q = """
    MATCH (si) WHERE elementId(si) = $in
    MATCH (sr) WHERE elementId(sr) = $out
    MERGE (si)-[:GENERATES]->(sr)
    """
    try:
        await cypher_query(q, {"in": input_id, "out": response_id})
    except Exception:
        pass


# ---- Utilities ---------------------------------------------------------------


async def _first_working_vector_query(
    index_names: list[str],
    k: int,
    vec: list[float],
) -> list[dict[str, Any]]:
    """
    Try each candidate index name with db.index.vector.queryNodes, return first hit.
    Returns [] if all fail or empty.

    We return rows with both the node *and* its elementId so downstream pairing queries
    can be robust across driver versions.
    """
    q = """
    CALL db.index.vector.queryNodes($index, $k, $vec)
    YIELD node, score
    RETURN elementId(node) AS id, node AS n, score
    """
    for name in index_names:
        try:
            rows = await cypher_query(q, {"index": name, "k": k, "vec": vec})
            if rows:
                return rows
        except Exception:
            # try next candidate
            pass
    return []


def _clip_messages(
    messages: list[dict[str, str]],
    hard_limit: int = MAX_CONTEXT_MESSAGES,
) -> list[dict[str, str]]:
    if len(messages) <= hard_limit:
        return messages
    # keep more recent by default
    return messages[-hard_limit:]


def _is_primitive(x: Any) -> bool:
    return isinstance(x, (str, int, float, bool))


# ---- Read context ------------------------------------------------------------


async def get_dynamic_user_context(
    *,
    user_id: str,
    session_id: str,
    user_input: str,
    recency_limit: int = 6,
    relevancy_limit: int = 6,
) -> dict[str, Any]:
    """
    Retrieves dynamic context for planning/synthesis:
      - recent_exchanges: last N turns for this session (user+assistant in order)
      - soul_profile: properties fetched from (u:SoulNode {uuid})-[:HAS_PROFILE]->(p:SoulProfile)
    """
    context: dict[str, Any] = {
        "recent_exchanges": [],
        "soul_profile": {},
    }

    # 1) Recent exchanges (for the active session)
    # Tolerate legacy property names and missing timestamps.
    RECENCY_QUERY = """
    MATCH (t)
    WHERE (t:SoulInput OR t:SoulResponse)
      AND coalesce(t.session_id, t.event_id) = $session_id
    WITH t
    ORDER BY coalesce(t.timestamp, datetime({epochMillis:0})) DESC
    LIMIT $lim
    WITH collect(t) AS ts
    UNWIND ts AS t
    WITH t
    ORDER BY coalesce(t.timestamp, datetime({epochMillis:0})) ASC
    RETURN
      CASE WHEN 'SoulInput' IN labels(t) THEN 'user' ELSE 'assistant' END AS role,
      t.text AS content,
      coalesce(t.timestamp, datetime({epochMillis:0})) AS ts
    """
    try:
        rows = await cypher_query(
            RECENCY_QUERY,
            {"session_id": session_id, "lim": recency_limit * 2},
        )
        # *** MODIFICATION: Preserve the timestamp for each message ***
        msgs = [
            {
                "role": r["role"],
                "content": r.get("content") or "",
                "timestamp": r["ts"].isoformat() if r.get("ts") else None,
            }
            for r in (rows or [])
        ]
        context["recent_exchanges"] = _clip_messages(msgs)
    except Exception as e:
        print(f"[UserProfile] recent_exchanges fetch failed: {e}")

    # 2) SoulProfile fetch (SoulNode graph)
    profile_q = """
    MATCH (u:SoulNode {uuid:$uid})-[:HAS_PROFILE]->(p:SoulProfile)
    RETURN p LIMIT 1
    """
    try:
        prow = (await cypher_query(profile_q, {"uid": user_id})) or []
        if prow:
            node = prow[0].get("p") or {}
            # Keep only primitive/array props (safe for prompt)
            safe_props = {
                k: v
                for k, v in (node.items() if isinstance(node, dict) else [])
                if _is_primitive(v) or (isinstance(v, list) and all(_is_primitive(x) for x in v))
            }
            context["soul_profile"] = safe_props
    except Exception as e:
        print(f"[UserProfile] soul_profile fetch failed: {e}")

    return context


# ---- Profile upsert (graph writes) -------------------------------------------


def _sanitize_profile_properties(patch: dict[str, Any]) -> dict[str, Any]:
    """
    Keep only JSON-primitive or array-of-primitive values.
    Drop nested maps to keep graph properties valid.
    """
    clean: dict[str, Any] = {}
    for k, v in (patch or {}).items():
        if v is None:
            continue
        if _is_primitive(v):
            clean[k] = v
        elif isinstance(v, list) and all(_is_primitive(x) for x in v):
            clean[k] = v
    return clean


async def ensure_soul_profile(user_id: str) -> None:
    """
    Guarantees:
      - (u:SoulNode {uuid:$uid}) exists
      - (u)-[:HAS_PROFILE]->(p:SoulProfile) exists
      - timestamps and ids maintained
    """
    q = """
    MERGE (u:SoulNode {uuid:$uid})
      ON CREATE SET
        u.created_at = datetime(),
        u.updated_at = datetime()
      ON MATCH SET
        u.updated_at = datetime()

    MERGE (u)-[:HAS_PROFILE]->(p:SoulProfile)
      ON CREATE SET
        p.created_at = datetime(),
        p.user_uuid  = $uid,
        p.user_id    = $uid,
        p.updated_at = datetime()
      ON MATCH SET
        p.user_uuid  = coalesce(p.user_uuid, $uid),
        p.user_id    = coalesce(p.user_id,  $uid),
        p.updated_at = datetime()
    """
    try:
        await cypher_query(q, {"uid": user_id})
    except Exception as e:
        print(f"[UserProfile] ensure_soul_profile failed: {e}")
        raise


async def upsert_soul_profile_properties(
    *,
    user_id: str,
    properties: dict[str, Any],
    source: str = "planner",
    confidence: float = 0.75,
) -> tuple[int, int]:
    """
    Upserts primitive/array props onto (u:SoulNode {uuid})-[:HAS_PROFILE]->(p:SoulProfile).
    Also writes immutable audit facts per key with confidence.
    Returns (props_upserted, facts_appended).
    """
    await ensure_soul_profile(user_id)
    props = _sanitize_profile_properties(properties)
    if not props:
        return (0, 0)

    set_q = """
    MATCH (u:SoulNode {uuid:$uid})-[:HAS_PROFILE]->(p:SoulProfile)
    SET p += $props,
        p.user_uuid  = coalesce(p.user_uuid, $uid),
        p.user_id    = coalesce(p.user_id,  $uid),
        p.updated_at = datetime()
    """
    try:
        print(f"[UserProfile] Upserting profile props for {user_id}: {props}")
        await cypher_query(set_q, {"uid": user_id, "props": props})
        props_upserted = len(props)
    except Exception as e:
        print(f"[UserProfile] property upsert failed: {e}")
        props_upserted = 0

    facts_q = """
    UNWIND $kv AS row
    MATCH (u:SoulNode {uuid:$uid})-[:HAS_PROFILE]->(p:SoulProfile)
    MERGE (p)-[:HAS_FACT]->(f:ProfileFact {user_uuid:$uid, key: row.k})
    ON CREATE SET f.created_at = datetime(), f.count = 0, f.values = [], f.user_id = $uid
    SET f.user_uuid = $uid,
        f.user_id   = $uid,
        f.last_source = $src,
        f.last_confidence = $conf,
        f.updated_at = datetime(),
        f.count = coalesce(f.count,0) + 1,
        f.values = CASE
          WHEN row.v IS NULL THEN f.values
          ELSE apoc.coll.toSet(coalesce(f.values,[]) + [row.v])
        END
    """
    try:
        kv = [{"k": k, "v": v} for k, v in props.items()]
        await cypher_query(
            facts_q,
            {"uid": user_id, "kv": kv, "src": source, "conf": float(confidence)},
        )
        facts_appended = len(kv)
    except Exception as e:
        print(f"[UserProfile] facts write (APOC) failed; falling back: {e}")
        facts_q_fallback = """
        UNWIND $kv AS row
        MATCH (u:SoulNode {uuid:$uid})-[:HAS_PROFILE]->(p:SoulProfile)
        MERGE (p)-[:HAS_FACT]->(f:ProfileFact {user_uuid:$uid, key: row.k})
        ON CREATE SET f.created_at = datetime(), f.count = 0, f.user_id = $uid
        SET f.user_uuid = $uid,
            f.user_id   = $uid,
            f.last_source = $src,
            f.last_confidence = $conf,
            f.last_value = row.v,
            f.updated_at = datetime(),
            f.count = coalesce(f.count,0) + 1
        """
        try:
            kv = [{"k": k, "v": v} for k, v in props.items()]
            await cypher_query(
                facts_q_fallback,
                {"uid": user_id, "kv": kv, "src": source, "conf": float(confidence)},
            )
            facts_appended = len(kv)
        except Exception as e2:
            print(f"[UserProfile] facts fallback failed: {e2}")
            facts_appended = 0

    return (props_upserted, facts_appended)


# ---- Orchestrator hook: single call for planner/synth ------------------------


async def build_context_for_voxis(
    *,
    user_id: str,
    session_id: str,
    user_input: str,
    recency_limit: int = 6,
    relevancy_limit: int = 6,
) -> dict[str, Any]:
    """
    One-shot context packer for planner & synthesis steps.
    """
    ctx = await get_dynamic_user_context(
        user_id=user_id,
        session_id=session_id,
        user_input=user_input,
        recency_limit=recency_limit,
        relevancy_limit=relevancy_limit,
    )
    return {
        "recent_exchanges": ctx.get("recent_exchanges", []),
        "soul_profile": ctx.get("soul_profile", {}),
    }


# ---- Schema-aware normalizers (LLM -> flat props) ----------------------------


def _merge_updates(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Shallow merge of sanitized updates; later items override earlier ones."""
    for k, v in (src or {}).items():
        dst[k] = v


def normalize_profile_upserts_from_llm(
    plan_obj: dict[str, Any],
    *,
    user_id: str | None = None,
    expected_user_id: str | None = None,  # alias used by pipeline
    min_confidence: float = 0.6,
) -> dict[str, Any]:
    """
    Accepts array shape:
      plan_obj["profile_upserts"] = [
        {"label":"SoulProfile","updates":{...},"confidence":0.9, ...}, ...
      ]
    Returns a flat dict of sanitized props to write.
    """
    target_user = user_id or expected_user_id
    props: dict[str, Any] = {}
    if not isinstance(plan_obj, dict):
        return props

    items = plan_obj.get("profile_upserts")
    if not isinstance(items, list):
        return props

    ALLOW_ANON = {None, "", "user_anon", "unknown"}

    for item in items:
        if not isinstance(item, dict):
            continue
        label = (item.get("label") or "").strip()
        if label != "SoulProfile":
            continue
        conf = float(item.get("confidence") or 0.0)
        if conf < float(min_confidence):
            continue

        mval = item.get("merge_value")
        if target_user:
            if mval not in ALLOW_ANON and str(mval) != str(target_user):
                continue

        updates = item.get("updates")
        if not isinstance(updates, dict):
            continue

        _merge_updates(props, _sanitize_profile_properties(updates))

    return props


def normalize_profile_upsert_from_llm(
    plan_obj: dict[str, Any],
    *,
    user_id: str | None = None,
    expected_user_id: str | None = None,
    min_confidence: float = 0.6,
) -> dict[str, Any]:
    # Try the new array shape first
    merged = normalize_profile_upserts_from_llm(
        plan_obj,
        user_id=user_id,
        expected_user_id=expected_user_id,
        min_confidence=min_confidence,
    )
    if merged:
        return merged

    # Fallback single-dict shapes
    candidate = None
    if isinstance(plan_obj, dict):
        candidate = plan_obj.get("profile_upsert")
        if not candidate and isinstance(plan_obj.get("analysis"), dict):
            prof = plan_obj["analysis"].get("profile")
            if isinstance(prof, dict):
                candidate = prof.get("upsert")

    if not isinstance(candidate, dict):
        return {}

    return _sanitize_profile_properties(candidate)
