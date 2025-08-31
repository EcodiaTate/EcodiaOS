from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _nums(blob: dict[str, Any], keys: Iterable[str]) -> float:
    tot = 0.0
    for k in keys:
        v = blob
        for p in k.split("."):
            if not isinstance(v, dict) or p not in v:
                v = None
                break
            v = v[p]
        if isinstance(v, int | float):
            tot += float(v)
    return tot


def compute_spent_ms(metrics_blob: dict[str, Any]) -> float:
    """
    Best-effort spend estimator from harvested timings.
    Assumes merge_metrics added repeated costs across calls.
    """
    return _nums(
        metrics_blob,
        [
            "llm.llm_latency_ms",
            "nova.propose_ms",
            "nova.evaluate_ms",
            "nova.auction_ms",
            "axon.action_cost_ms",
        ],
    )


def ensure_budget_fields(metrics_blob: dict[str, Any]) -> dict[str, Any]:
    """
    Non-destructively add correlation.spent_ms if missing.
    Return the (possibly) augmented blob.
    """
    corr = metrics_blob.setdefault("correlation", {})
    if "spent_ms" not in corr:
        corr["spent_ms"] = round(compute_spent_ms(metrics_blob), 1)
    return metrics_blob
