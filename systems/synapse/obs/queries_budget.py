from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query


def _window_ms(days: int) -> int:
    days = max(1, min(365, int(days or 30)))
    return days * 86_400_000  # ms


async def get_budget_series(days: int = 30) -> list[dict[str, Any]]:
    """
    Return daily SUM for correlation.allocated_ms and correlation.spent_ms.
    Output rows: {name, day, sum_value}
    """
    q = """
    MATCH (e:Episode)
    WHERE e.timestamp >= (timestamp() - $since_ms)
    WITH date(datetime({ epochMillis: e.timestamp })) AS day,
         toFloat(e.metrics["correlation.allocated_ms"]) AS alloc,
         toFloat(e.metrics["correlation.spent_ms"])     AS spent
    RETURN
      "correlation.allocated_ms" AS name, day, sum(alloc) AS sum_value
    UNION ALL
    MATCH (e:Episode)
    WHERE e.timestamp >= (timestamp() - $since_ms)
    WITH date(datetime({ epochMillis: e.timestamp })) AS day,
         toFloat(e.metrics["correlation.spent_ms"]) AS spent
    RETURN
      "correlation.spent_ms" AS name, day, sum(spent) AS sum_value
    ORDER BY day ASC
    """
    return await cypher_query(q, {"since_ms": _window_ms(days)})
