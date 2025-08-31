# systems/simula/review/atune_summary.py
from __future__ import annotations

from typing import Any


def summarize_atune(detail: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize Atune/Unity review detail into a compact summary the LLM can observe.
    Expects one item's detail from Orchestrator's atune route response.
    """
    status = str(detail.get("status", "unknown"))
    escalated = status.startswith("escalated_")
    pvals = detail.get("pvals") or {}
    plan = detail.get("plan") or {}
    unity = detail.get("unity_result") or {}
    return {
        "status": status,
        "escalated": escalated,
        "salience_p": float(pvals.get("salience") or pvals.get("salient") or 0.0),
        "safety_p": float(pvals.get("safety") or 0.0),
        "plan_steps": len(plan.get("steps") or []),
        "unity_summary": {
            "actors": list((unity.get("actors") or {}).keys()),
            "decision": unity.get("decision"),
            "notes": unity.get("notes"),
        },
    }
