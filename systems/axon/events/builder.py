# systems/axon/events/builder.py
from __future__ import annotations

from typing import Any

from systems.axon.schemas import ActionResult, AxonIntent


def _base_event(intent: AxonIntent, result: ActionResult, event_type: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": {
            "source": "axon",
            "topic": f"axon::{event_type}",
            "payload": details,
            "intent": {
                "id": intent.intent_id,
                "capability": intent.target_capability,
                "risk_tier": getattr(intent, "risk_tier", None),
            },
            "result_meta": {
                "status": result.status,
                "driver_name": (getattr(result, "outputs", {}) or {}).get("driver_name"),
            },
            "raw": None,
        }
    }

def build_followups(intent: AxonIntent, result: ActionResult) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    outputs = getattr(result, "outputs", {}) or {}
    status = getattr(result, "status", "unknown")

    # Always: compact result summary
    out.append(
        _base_event(
            intent,
            result,
            "action.result",
            {
                "status": status,
                "summary": outputs.get("summary") or outputs.get("message") or "",
                "metrics": getattr(result, "counterfactual_metrics", {}) or {},
            },
        ),
    )

    # Search → search.results
    search_hits = outputs.get("hits") or outputs.get("results")
    if isinstance(search_hits, list) and search_hits:
        top: list[dict[str, Any]] = []
        for h in search_hits[:10]:
            if not isinstance(h, dict):
                continue
            top.append(
                {
                    "title": str(h.get("title", ""))[:200],
                    "url": str(h.get("url", ""))[:400],
                    "snippet": str(h.get("snippet", ""))[:400],
                    "score": float(h.get("score", 0.0)) if h.get("score") is not None else None,
                },
            )
        if top:
            out.append(
                _base_event(
                    intent,
                    result,
                    "search.results",
                    {
                        "query": (getattr(intent, "params", {}) or {}).get("query", ""),
                        "results": top,
                    },
                ),
            )

    return out
