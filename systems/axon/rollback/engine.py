# systems/axon/rollback/engine.py
from __future__ import annotations

import copy
import time
from typing import Any

from systems.axon.mesh.registry import DriverRegistry
from systems.axon.schemas import ActionResult, AxonIntent


async def execute_rollback(
    intent: AxonIntent,
    result: ActionResult,
    registry: DriverRegistry,
) -> dict[str, Any]:
    """
    Execute a simple rollback contract if present on the original intent:
      intent.rollback_contract = {"capability":"<cap>","params":{...}}
    Returns a dict with status and optional rollback ActionResult.
    """
    rb = getattr(intent, "rollback_contract", {}) or {}
    cap = rb.get("capability")
    if not cap:
        return {"status": "no_rollback"}

    driver = registry.get_live_driver_for_capability(cap)
    if not driver:
        return {"status": "rollback_no_driver", "capability": cap}

    # Construct rollback intent
    rb_intent = copy.deepcopy(intent)
    rb_intent.intent_id = f"{intent.intent_id}::rollback"
    rb_intent.target_capability = cap
    rb_intent.params = copy.deepcopy(rb.get("params", {}))
    rb_intent.constraints = {"dry_run": False}

    try:
        t0 = time.perf_counter()
        rb_res: ActionResult = await driver.push(rb_intent)
        return {
            "status": "rollback_executed",
            "latency_ms": (time.perf_counter() - t0) * 1000.0,
            "result": {
                "status": rb_res.status,
                "outputs": rb_res.outputs,
                "counterfactual_metrics": rb_res.counterfactual_metrics,
            },
        }
    except Exception as e:
        return {"status": "rollback_failed", "error": str(e)}
