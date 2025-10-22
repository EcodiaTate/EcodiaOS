# systems/axon/ab/runner.py
from __future__ import annotations

import copy
import time
from typing import Any

from systems.axon.dependencies import get_driver_registry, get_scorecard_manager
from systems.axon.learning.feedback import ingest_action_outcome
from systems.axon.safety.twin import run_in_twin
from systems.axon.schemas import ActionResult, AxonIntent


def _mk_shadow_intent(intent: AxonIntent, shadow_name: str) -> AxonIntent:
    shadow = copy.deepcopy(intent)
    shadow.intent_id = f"{intent.intent_id}::ab::{shadow_name[:8]}"
    constraints = dict(shadow.constraints or {})
    constraints["dry_run"] = True
    shadow.constraints = constraints
    if isinstance(shadow.policy_trace, dict):
        shadow.policy_trace["ab_parent"] = intent.intent_id
    return shadow


async def run_ab_trial(intent: AxonIntent, *, decision_id: str | None = None) -> dict[str, Any]:
    reg = get_driver_registry()
    cards = get_scorecard_manager()
    cap = intent.target_capability
    out: dict[str, Any] = {
        "capability": cap,
        "intent_id": intent.intent_id,
        "twin": None,
        "shadows": [],
    }

    # Twin prediction (baseline)
    t0 = time.perf_counter()
    twin_res: ActionResult = await run_in_twin(intent)
    twin_ms = (time.perf_counter() - t0) * 1000.0
    out["twin"] = {
        "status": twin_res.status,
        "latency_ms": twin_ms,
        "counterfactual_metrics": twin_res.counterfactual_metrics,
        "outputs": twin_res.outputs,
    }

    # Shadows (dry-run)
    shadows = reg.get_shadow_drivers_for_capability(cap) or []
    for sh in shadows:
        name = sh.describe().driver_name
        sh_intent = _mk_shadow_intent(intent, name)
        t1 = time.perf_counter()
        try:
            res: ActionResult = await sh.push(sh_intent)
            lat = (time.perf_counter() - t1) * 1000.0
            out["shadows"].append(
                {
                    "driver": name,
                    "status": res.status,
                    "latency_ms": lat,
                    "counterfactual_metrics": res.counterfactual_metrics,
                    "outputs": res.outputs,
                },
            )
            # score uplift vs twin; send to Synapse ingest_outcome
            upl = res.counterfactual_metrics.get(
                "actual_utility",
                0.0,
            ) - twin_res.counterfactual_metrics.get("predicted_utility", 0.0)
            cards.update_scorecard(
                name,
                was_successful=(res.status == "ok"),
                latency_ms=lat,
                uplift=upl,
            )
            await ingest_action_outcome(
                intent=sh_intent,
                predicted_result=twin_res,
                actual_result=res,
                decision_id=decision_id,
            )

        except Exception as e:
            lat = (time.perf_counter() - t1) * 1000.0
            out["shadows"].append(
                {"driver": name, "status": "fail", "latency_ms": lat, "error": str(e)},
            )
            cards.update_scorecard(name, was_successful=False, latency_ms=lat, uplift=0.0)
            try:
                fail_res = ActionResult(
                    intent_id=sh_intent.intent_id,
                    status="fail",
                    outputs={"error": "shadow_exception", "details": str(e)},
                    side_effects={},
                    counterfactual_metrics={"actual_utility": 0.0},
                )
                await ingest_action_outcome(
                    intent=sh_intent,
                    predicted_result=twin_res,
                    actual_result=fail_res,
                    decision_id=decision_id,
                )
            except Exception:
                pass

    return out
