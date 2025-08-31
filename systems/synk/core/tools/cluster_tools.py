# systems/unity/tools/cluster_tools.py
from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query


async def fetch_cluster_context_tool(
    driver_like: Any,
    context: dict[str, Any],
    *,
    cluster_keys: list[str],
    per_cluster: int = 5,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Fetch up to `per_cluster` recent member events for each cluster_key.
    Returns { "<cluster_key>": { "members": [...], "size": int } }
    """
    if not cluster_keys:
        return {}

    out: dict[str, Any] = {}
    q = """
    MATCH (c:Cluster {cluster_key: $key})<-[:IN_CLUSTER]-(e:Event)
    WITH c, e
    ORDER BY e.created_at DESC
    WITH c, collect({
        event_id: e.event_id,
        created_at: e.created_at,
        summary: coalesce(e.summary, ""),
        content: coalesce(e.content, ""),
        cluster_id: c.cluster_id
    }) AS members
    RETURN size(members) AS size, members[0..$limit] AS sample
    """

    for key in cluster_keys:
        rows = await cypher_query(q, {"key": key, "limit": int(per_cluster)})
        row = rows[0] if rows else {}
        out[key] = {
            "size": int(row.get("size", 0)),
            "members": row.get("sample", []),
        }

    return out
