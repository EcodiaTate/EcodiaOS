# systems/atune/metrics/budget_audit.py
from __future__ import annotations

from typing import Any

from core.metrics.registry import REGISTRY


def audit_and_record(intent_budget_ms: int, axon_result: dict[str, Any]) -> tuple[int, int, float]:
    """
    Reads Axon-reported cost and emits gauges/counters.
    Expects axon_result like: {"status":"ok", "metrics":{"cost_ms":123, ...}} (best-effort).
    Returns: (reported_cost_ms, delta_ms, delta_pct)
    """
    m = (axon_result or {}).get("metrics") or {}
    reported = int(m.get("cost_ms", -1))
    if reported < 0:
        return (-1, 0, 0.0)
    delta = reported - int(intent_budget_ms)
    pct = (float(delta) / max(1.0, float(intent_budget_ms))) * 100.0
    try:
        REGISTRY.gauge("atune.intent.cost_reported_ms").set(reported)
        REGISTRY.gauge("atune.intent.cost_alloc_ms").set(intent_budget_ms)
        REGISTRY.gauge("atune.intent.cost_delta_ms").set(delta)
        REGISTRY.gauge("atune.intent.cost_delta_pct").set(pct)
    except Exception:
        pass
    return (reported, delta, pct)
