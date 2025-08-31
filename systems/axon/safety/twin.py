# systems/axon/safety/twin.py
from __future__ import annotations

import time
from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.axon.schemas import ActionResult, AxonIntent


async def _post_json(path: str, body: dict[str, Any]) -> dict[str, Any]:
    client = await get_http_client()
    r = await client.post(path, json=body, headers={"x-budget-ms": "800"})
    r.raise_for_status()
    return r.json()

async def run_in_twin(intent: AxonIntent) -> ActionResult:
    """
    Produce a counterfactual prediction for an intent.
    Prefers Synapse's SIMULATE op; falls back to Simula twin eval.
    """
    body = intent.model_dump()
    started = time.perf_counter()

    path = None
    try:
        # Preferred: Synapse simulate (per bible's canonical ops)
        if hasattr(ENDPOINTS, "SYNAPSE_SIMULATE"):
            path = ENDPOINTS.SYNAPSE_SIMULATE
        # Fallback: Simula twin eval, also using the overlay
        elif hasattr(ENDPOINTS, "SIMULA_TWIN_EVAL"):
            path = ENDPOINTS.SIMULA_TWIN_EVAL
        
        if not path:
             raise ValueError("No simulation endpoint (SYNAPSE_SIMULATE or SIMULA_TWIN_EVAL) found in API overlay.")

        data = await _post_json(path, body)

    except Exception as e:
        # Fail-safe prediction (prevents downstream overconfidence)
        dur_ms = (time.perf_counter() - started) * 1000.0
        return ActionResult(
            intent_id=intent.intent_id,
            status="blocked",
            outputs={"error": "twin_unavailable", "details": str(e)},
            side_effects={},
            counterfactual_metrics={"predicted_utility": 0.0, "twin_latency_ms": dur_ms},
        )

    dur_ms = (time.perf_counter() - started) * 1000.0
    # Normalize minimal shape expected by callers
    counterfactual = data.get("counterfactual_metrics") or {}
    counterfactual.setdefault("predicted_utility", float(counterfactual.get("predicted_utility", 0.0)))
    counterfactual["twin_latency_ms"] = dur_ms

    return ActionResult(
        intent_id=intent.intent_id,
        status=data.get("status", "ok"),
        outputs=data.get("outputs", {}),
        side_effects=data.get("side_effects", {}),
        counterfactual_metrics=counterfactual,
        follow_up_events=[],
    )