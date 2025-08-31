from __future__ import annotations

from core.utils.neo.cypher_query import cypher_query

ROLLUP = """
UNWIND $metric_keys AS k
MATCH (e:Episode)
WHERE e.timestamp >= timestamp() - $window_ms AND e.metrics[k] IS NOT NULL
WITH k, datetime({epochMillis: e.timestamp}) AS dt, toFloat(e.metrics[k]) AS v
WITH k, datetime({year: dt.year, month: dt.month, day: dt.day, hour: dt.hour}) AS hour, v
RETURN k AS key, hour AS hour, avg(v) AS avg_v, percentileCont(v,0.95) AS p95_v, count(*) AS n
"""

UPSERT = """
MERGE (b:MetricBucket {key: $key, hour: $hour})
ON CREATE SET b.created_ts = timestamp()
SET b.avg = $avg, b.p95 = $p95, b.n = $n, b.updated_ts = timestamp()
"""


async def rollup_hourly(metric_keys: list[str], hours: int = 24) -> int:
    rows = await cypher_query(ROLLUP, {"metric_keys": metric_keys, "window_ms": hours * 3_600_000})
    count = 0
    for r in rows:
        await cypher_query(
            UPSERT,
            {
                "key": r["key"],
                "hour": str(r["hour"]),
                "avg": r["avg_v"],
                "p95": r["p95_v"],
                "n": r["n"],
            },
        )
        count += 1
    return count
