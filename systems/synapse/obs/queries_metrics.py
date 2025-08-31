# file: systems/synapse/obs/queries_metrics.py
from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query

# --- internal helpers ---------------------------------------------------------


def _metric_key(name: str, scope: str | None) -> str:
    """Return the exact key stored inside Episode.metrics (flat-but-namespaced)."""
    dotted = (name or "").strip()
    if "." in dotted:
        return dotted
    return f"{scope}.{name}" if scope else name


def _group_key(group_by: str | None) -> str | None:
    """
    Map friendly group_by to a metrics key. Examples:
      - "provider" → "llm.provider"
      - "model"    → "llm.model"
      - "arm_id"   → "correlation.arm_id"
      - "decision_id" → "correlation.decision_id"
      - already-namespaced keys pass through (e.g., "axon.action_cost_ms")
    """
    if not group_by:
        return None
    gb = group_by.strip()
    if gb in {"provider", "model"}:
        return f"llm.{gb}"
    if gb in {"arm_id", "decision_id"}:
        return f"correlation.{gb}"
    return gb  # assume caller passed a namespaced tag


def _window_ms(days: int) -> int:
    days = max(1, min(365, int(days or 30)))
    return days * 86_400_000  # ms


# --- public API used by systems.synapse.obs.metrics_api -----------------------


async def get_metric_series(
    name: str,
    *,
    scope: str | None = None,
    system: str | None = None,
    days: int = 30,
    group_by: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return daily AVG for a given Episode.metrics key, optionally grouped by a tag.
    Reads from (:Episode {timestamp, system, metrics{...}}) with metrics stored flat, e.g.:
      metrics["llm.llm_latency_ms"], metrics["llm.provider"], metrics["correlation.arm_id"], ...
    """
    metric_key = _metric_key(name, scope)
    group_key = _group_key(group_by)

    q = """
    MATCH (e:Episode)
    WHERE e.timestamp >= (timestamp() - $since_ms)
      AND ($system IS NULL OR toLower(coalesce(e.system, e.agent, "")) = toLower($system))

    WITH
      coalesce(e.system, e.agent, "")                    AS system,
      date(datetime({ epochMillis: e.timestamp }))       AS day,
      CASE
        WHEN $group_key IS NULL THEN ""
        ELSE toString(e.metrics[$group_key])
      END                                                AS tag,
      toFloat(e.metrics[$metric_key])                    AS v

    WHERE v IS NOT NULL
    RETURN
      $name AS name,
      $scope AS scope,
      system,
      tag,
      day,
      avg(v) AS avg_value
    ORDER BY day ASC
    """
    params = {
        "since_ms": _window_ms(days),
        "system": system,
        "metric_key": metric_key,
        "group_key": group_key,
        "name": name,
        "scope": scope or "",
    }
    return await cypher_query(q, params)


async def get_agents_overview(days: int = 30) -> list[dict[str, Any]]:
    """
    Aggregate per-agent calls, latency (avg & p95), tokens, and success rate.
    Latency derives from metrics["llm.llm_latency_ms"] when present.
    """
    q = """
    MATCH (e:Episode)
    WHERE e.timestamp >= (timestamp() - $since_ms)

    WITH
      coalesce(e.system, e.agent, "unknown")             AS agent,
      toFloat(e.metrics["llm.llm_latency_ms"])           AS lat,
      toInteger(e.metrics["llm.prompt_tokens"])          AS pt,
      toInteger(e.metrics["llm.completion_tokens"])      AS ct,
      CASE WHEN e.metrics["success.ok"] = true THEN 1 ELSE 0 END AS ok

    RETURN
      agent,
      count(*)                                           AS calls,
      avg(lat)                                           AS avg_latency_ms,
      percentileCont(lat, 0.95)                          AS p95_latency_ms,
      sum(pt)                                            AS prompt_tokens,
      sum(ct)                                            AS completion_tokens,
      CASE WHEN count(*) = 0 THEN 0.0
           ELSE toFloat(sum(ok)) / count(*)
      END                                                AS success_rate
    ORDER BY calls DESC
    """
    return await cypher_query(q, {"since_ms": _window_ms(days)})


async def get_arm_leaderboard(days: int = 30, top_k: int = 5) -> dict[str, list[dict[str, Any]]]:
    """
    Rank arms by success_rate then calls. Also show bottom slice for quick triage.
    success_rate uses metrics["success.ok"] booleans.
    """
    base = """
    MATCH (e:Episode)
    WHERE e.timestamp >= (timestamp() - $since_ms)

    WITH
      toString(e.metrics["correlation.arm_id"])          AS arm_id,
      CASE WHEN e.metrics["success.ok"] = true THEN 1 ELSE 0 END AS ok,
      toFloat(e.metrics["llm.llm_latency_ms"])           AS lat,
      toFloat(e.metrics["eval.avg_candidate_cost_ms"])   AS eval_cost

    WHERE arm_id IS NOT NULL AND arm_id <> ""
    RETURN
      arm_id,
      count(*)                                           AS calls,
      avg(lat)                                           AS avg_latency_ms,
      avg(eval_cost)                                     AS avg_eval_cost_ms,
      toFloat(sum(ok)) / count(*)                        AS success_rate
    """

    top_q = base + "\nORDER BY success_rate DESC, calls DESC LIMIT $top_k"
    bottom_q = base + "\nORDER BY success_rate ASC, calls DESC LIMIT $top_k"

    params = {"since_ms": _window_ms(days), "top_k": max(1, min(20, int(top_k)))}

    top_rows = await cypher_query(top_q, params)
    bottom_rows = await cypher_query(bottom_q, params)

    return {"top": top_rows, "bottom": bottom_rows}
