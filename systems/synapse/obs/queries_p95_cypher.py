from __future__ import annotations

# Pure-Cypher p95 (no APOC). If metrics are flattened on the Episode node as keys like "llm_llm_latency_ms".
P95_QUERY_TPL = """
MATCH (e:Episode)
WHERE e.timestamp >= $since_ts
WITH e, e[$metric_key] AS v
WHERE v IS NOT NULL
RETURN percentileCont(v, 0.95) AS p95
"""


def p95_query(metric_key: str) -> str:
    return P95_QUERY_TPL
