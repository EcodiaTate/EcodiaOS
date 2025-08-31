# systems/axon/core/act.py
from __future__ import annotations

import time
from typing import Any

from systems.axon.dependencies import (
    get_circuit_breaker,
    get_conformal_predictor,
    get_contracts_engine,
    get_driver_registry,
    get_journal,
    get_scorecard_manager,
)
from systems.axon.events.builder import build_followups
from systems.axon.events.emitter import emit_followups_bg
from systems.axon.learning.feedback import ingest_action_outcome
# highlight-start
from systems.axon.safety.validation import CapabilityValidator
# highlight-end
from systems.axon.safety.twin import run_in_twin
from systems.axon.schemas import ActionResult, AxonIntent


async def execute_intent(intent: AxonIntent, *, decision_id: str | None = None) -> ActionResult:
    """
    Full Axon act pipeline: auth -> pre -> twin -> conformal -> circuit -> push -> post -> followups/journal -> feedback
    """
    registry = get_driver_registry()
    scorecards = get_scorecard_manager()
    conformal = get_conformal_predictor()
    breaker = get_circuit_breaker()
    contracts = get_contracts_engine()
    journal = get_journal()
# highlight-start
    validator = CapabilityValidator()

    # -------- Ingress & auth --------
    if not validator.validate(intent, driver_registry=registry):
        res = ActionResult(
            intent_id=intent.intent_id,
            status="blocked",
            outputs={"error": "equor_token_validation_failed"},
            side_effects={},
            counterfactual_metrics={},
        )
        try:
            journal.write_entry(res)
        except Exception:
            pass
        return res
# highlight-end

    # -------- preconditions --------
    pre = contracts.check_pre(intent)
    if not pre.ok:
        res = ActionResult(
            intent_id=intent.intent_id,
            status="blocked",
            outputs={"error": "preconditions_failed", "reason": pre.reason, "patches": pre.patches},
            side_effects={},
            counterfactual_metrics={},
        )
        try:
            journal.write_entry(res)
        except Exception:
            pass
        return res

    # -------- twin prediction --------
    twin = await run_in_twin(intent)
    predicted = float(twin.counterfactual_metrics.get("predicted_utility", 0.0))

    # -------- conformal bound --------
    bound = conformal.bound(predicted)

    # -------- circuit breaker --------
    cap = intent.target_capability
    if not breaker.allow(cap):
        res = ActionResult(
            intent_id=intent.intent_id,
            status="blocked",
            outputs={"error": "circuit_open"},
            side_effects={},
            counterfactual_metrics={"predicted_utility": predicted, "conformal": bound.__dict__},
        )
        try:
            journal.write_entry(res)
        except Exception:
            pass
        return res

    # -------- driver push (live) --------
    live = registry.get_live_driver_for_capability(cap)
    if live is None:
        res = ActionResult(
            intent_id=intent.intent_id,
            status="fail",
            outputs={"error": "no_live_driver", "capability": cap},
            side_effects={},
            counterfactual_metrics={"predicted_utility": predicted, "conformal": bound.__dict__},
        )
        try:
            journal.write_entry(res)
        except Exception:
            pass
        return res

    t0 = time.perf_counter()
    try:
        result = await live.push(intent)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        breaker.report(cap, ok=(result.status == "ok"))
        actual_util = float(result.counterfactual_metrics.get("actual_utility", predicted))
        conformal.observe(predicted=predicted, actual=actual_util)

        # -------- postconditions --------
        post = contracts.check_post(intent, result)
        if not post.ok:
            # (Optional) rollback example
            rollback_status = "skipped"
            if getattr(intent, "rollback_contract", None):
                try:
                    rb = AxonIntent(
                        **{
                            **intent.model_dump(),
                            "intent_id": f"{intent.intent_id}::rollback",
                            "params": intent.rollback_contract.get("params", {}),
                        }
                    )
                    rb_res = await live.push(rb)
                    rollback_status = f"rollback_{rb_res.status}"
                except Exception as e:
                    rollback_status = f"rollback_fail:{e}"

            result = ActionResult(
                intent_id=intent.intent_id,
                status="fail",
                outputs={"error": "postconditions_failed", "reason": post.reason, "rollback": rollback_status},
                side_effects=result.side_effects,
                counterfactual_metrics=result.counterfactual_metrics,
                follow_up_events=result.follow_up_events,
            )

        # -------- follow-ups + journal --------
        try:
            for ev in build_followups(intent, result):
                emit_followups_bg([ev], decision_id=decision_id)
        except Exception:
            pass
        try:
            journal.write_entry(result)
        except Exception:
            pass

        # -------- scorecards --------
        upl = float(result.counterfactual_metrics.get("actual_utility", predicted) - predicted)
        scorecards.update_scorecard(
            live.describe().driver_name,
            was_successful=(result.status == "ok"),
            latency_ms=latency_ms,
            uplift=upl,
        )

        # -------- learning feedback (predicted vs actual) --------
        try:
            await ingest_action_outcome(intent=intent, predicted_result=twin, actual_result=result, decision_id=decision_id)
        except Exception:
            pass

        return result

    except Exception as e:
        breaker.report(cap, ok=False)
        res = ActionResult(
            intent_id=intent.intent_id,
            status="fail",
            outputs={"error": "driver_exception", "details": str(e)},
            side_effects={},
            counterfactual_metrics={"predicted_utility": predicted, "conformal": bound.__dict__},
        )
        try:
            journal.write_entry(res)
        except Exception:
            pass
        # still emit a feedback record for learning
        try:
            await ingest_action_outcome(intent=intent, predicted_result=twin, actual_result=res, decision_id=decision_id)
        except Exception:
            pass
        return res