# systems/atune/planner/secl_orchestrator.py
from __future__ import annotations

from typing import Any

from systems.atune.gaps.orchestrator import submit_capability_gap
from systems.atune.intent.constraints_merge import merge_playbook_into_constraints
from systems.atune.intent.gap_detector import detect_capability_gap
from systems.synapse.sdk.hints_extras import HintsExtras  # canonical

# Optional: conformal gating if you want to use it here
try:
    from systems.atune.safety.gating import ConformalGate
except Exception:
    ConformalGate = None  # type: ignore


class SECLSignals:
    """
    Planner-facing signals bundle (all optional, pass what you have).
    """

    def __init__(
        self,
        head_pvals: dict[str, float] | None = None,
        postcond_errors: list[dict[str, Any]] | None = None,
        regret_window: list[float] | None = None,
        trending_hosts: list[str] | None = None,
        exemplars: list[dict[str, Any]] | None = None,
        incumbent_driver: str | None = None,
    ):
        self.head_pvals = head_pvals or {}
        self.postcond_errors = postcond_errors or []
        self.regret_window = regret_window or []
        self.trending_hosts = trending_hosts or []
        self.exemplars = exemplars or []
        self.incumbent_driver = incumbent_driver


async def prepare_intent_with_secl(
    *,
    decision_id: str,
    intent: dict[str, Any],
    known_capabilities: list[str],
    signals: SECLSignals,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Returns (final_intent, context) where:
      - final_intent has merged constraints + populated rollback_contract (if playbook available)
      - context has {"secl": {...}, "hints": {...}} for logging/WhyTrace

    'intent' expected shape (min): {
        "capability": "qora.search",
        "constraints": {...}    # optional
    }
    """
    ctx: dict[str, Any] = {"secl": {}, "hints": {}}
    final_intent: dict[str, Any] = dict(intent)

    # 0) (Optional) conformal gate — if you haven't run it yet in your pipeline
    if ConformalGate and signals.head_pvals:
        gate = ConformalGate(default_alpha=0.1)
        verdict = await gate.decide(signals.head_pvals, context={"decision_id": decision_id})
        ctx["secl"]["conformal"] = {
            "alpha_used": verdict.alpha_used,
            "per_head_alpha": verdict.per_head_alpha,
            "head_pvals": verdict.head_pvals,
            "escalate": verdict.escalate,
            "reason": getattr(verdict.reason, "detail", None) if verdict.reason else None,
        }
        final_intent.setdefault("meta", {})["conformal_verdict"] = ctx["secl"]["conformal"]

    # 1) Detect capability gap
    chosen_cap = str(final_intent.get("capability", "") or "")
    gap = detect_capability_gap(
        decision_id=decision_id,
        chosen_capability=chosen_cap or None,
        known_capabilities=known_capabilities,
        postcond_errors=signals.postcond_errors,
        regret_window=signals.regret_window,
        trending_hosts=signals.trending_hosts,
        exemplars=signals.exemplars,
        incumbent_driver=signals.incumbent_driver,
    )

    gap_result: dict[str, Any] | None = None

    # 2) If gap → call Probecraft intake (synthesis/discovery + playbook + A/B)
    if gap is not None:
        gap_result = await submit_capability_gap(gap, headers=headers or {})
        ctx["secl"]["gap_emitted"] = True
        ctx["secl"]["gap_result"] = gap_result
        # If Probecraft returns a realized capability, update
        driver = (gap_result or {}).get("driver") or {}
        realized_cap = driver.get("capability")
        if realized_cap:
            final_intent["capability"] = realized_cap

        # 3) Merge Unity playbook into constraints + synthesize rollback
        playbook = (gap_result or {}).get("playbook") or {}
        merged_constraints, rollback_contract = merge_playbook_into_constraints(
            base_constraints=final_intent.get("constraints"),
            playbook=playbook,
        )
        final_intent["constraints"] = merged_constraints
        if rollback_contract:
            final_intent["rollback_contract"] = rollback_contract

    else:
        ctx["secl"]["gap_emitted"] = False

    # 4) Pull Synapse pricing hints (cost-aware auction) and add to context
    hints = HintsExtras()
    price_per_cap = await hints.price_per_capability(context={"decision_id": decision_id})
    ctx["hints"]["price_per_capability"] = price_per_cap

    return final_intent, ctx
