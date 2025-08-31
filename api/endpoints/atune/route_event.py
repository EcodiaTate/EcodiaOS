# api/endpoints/atune/route_event.py
from __future__ import annotations

import hashlib
import hmac
import os
import time as pytime
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, Header

from core.metrics.registry import REGISTRY
from core.prompting.orchestrator import plan_deliberation
from core.utils.net_api import ENDPOINTS, get_http_client

from systems.atune.budgeter.manager import AttentionBudgetManager
from systems.atune.budgeter.reserves import apply_hinted_reserves
from systems.atune.budgeter.tempo import TempoForecaster
from systems.atune.control.affect import AffectiveControlLoop, AffectiveState
from systems.atune.escalation.build import build_escalation_payload
from systems.atune.escalation.reasons import reason_conformal_ood
from systems.atune.focus.field import SalienceFieldManager
from systems.atune.focus.tuner import DiffusionTuner
from systems.atune.ingest.followups import harvest_batch_followups, salience_hints_from_harvest
from systems.atune.journal.ledger import ReplayCapsule, WhyTrace, record
from systems.atune.journal.why_helpers import summarize_pareto_knee
from systems.atune.knowledge.graph_interface import KnowledgeGraphInterface
from systems.atune.memory.induction import SchemaInducer
from systems.atune.memory.store import MemoryStore
from systems.atune.metrics.budget_audit import audit_and_record
from systems.atune.metrics.secl_counters import bump as secl_bump
from systems.atune.metrics.secl_counters import set_gauge as secl_set_gauge
from systems.atune.metrics.secl_counters import set_info as secl_set_info
from systems.atune.planner.costs import scale_bid_costs
from systems.atune.planner.fae import FAE_Calculator, FAEScore
from systems.atune.planner.inference import ActiveInferenceHead
from systems.atune.planner.known_caps import get_known_capabilities
from systems.atune.planner.market import AttentionMarket, Bid
from systems.atune.planner.secl_orchestrator import SECLSignals, prepare_intent_with_secl
from systems.atune.planner.strategy import resolve_market_strategy
from systems.atune.probes.engine import ProbeEngine
from systems.atune.processing.canonical import Canonicalizer
from systems.atune.safety.reflex_catalog import apply_redactions
from systems.atune.safety.reflex_catalog import decide as reflex_decide
from systems.atune.salience.conformal import PerHeadConformal
from systems.atune.salience.conformal_alpha_adapter import apply_alpha_hints
from systems.atune.salience.engine import SalienceEngine
from systems.atune.salience.gating import MetaAttentionGater
from systems.atune.salience.heads import KeywordHead, NoveltyHead, RiskHead

from systems.axon.schemas import AxonEvent, AxonIntent
from systems.axon.safety.validation import Predicate

from systems.equor.kms.keystore import get_active_kid, get_hmac_key_by_kid
from core.llm.embeddings_gemini import get_embedding
# Synapse typed SDK (policy, budget, hints)
from systems.synapse.sdk.client import SynapseClient
from systems.synapse.sdk.hints_client import SynapseHintsClient
from systems.synapse.sdk.hints_extras import HintsExtras

route_router = APIRouter()
# Optional alias if other modules import `router`
router = route_router

# ---------- Deterministic components (no local policy learning) --------------
canonicalizer = Canonicalizer()
probe_engine = ProbeEngine()
fae_calculator = FAE_Calculator(lambda_epi=0.8, lambda_risk=1.5, lambda_cost=0.1)
attention_market = AttentionMarket()
budget_manager = AttentionBudgetManager(pool_ms_per_tick=20000)
tempo_forecaster = TempoForecaster()
kg_interface = KnowledgeGraphInterface()
salience_field_manager = SalienceFieldManager()
affective_control_loop = AffectiveControlLoop()
memory_store = MemoryStore()
schema_inducer = SchemaInducer()
active_inference_head = ActiveInferenceHead()
per_head_conformal = PerHeadConformal(window=512, alpha=0.05)
tuner = DiffusionTuner(leak_gamma=float(os.getenv("ATUNE_GAMMA_DEFAULT", "0.15")))

risk_patterns = {
    "PII_SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "CONFIDENTIAL_MARKER": r"\b(confidential|secret|internal use only)\b",
}
salience_engine = SalienceEngine(
    heads=[KeywordHead(critical_keywords=["security breach", "system failure", "urgent"]),
           NoveltyHead(),
           RiskHead(threat_patterns=risk_patterns)],
)
meta_attention_gater = MetaAttentionGater(context_dim=2, num_heads=len(salience_engine.head_names))
# -----------------------------------------------------------------------------

def _best_actual_utility(candidates: list[dict[str, Any]]) -> float:
    best = 0.0
    for c in candidates:
        try:
            u = float((c.get("counterfactual_metrics") or {}).get("actual_utility", 0.0))
            if u > best:
                best = u
        except Exception:
            pass
    return best

def _sign_token(
    intent_id: str,
    predicates: list[Predicate],
    capability: str,
    artifact_hash: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """
    KMS-backed HMAC token signer (kid rotates via KMS).
    """
    now = int(pytime.time())
    kid = get_active_kid()
    key = get_hmac_key_by_kid(kid)
    if not key:
        raise RuntimeError("No KMS key available to sign capability token")

    message = intent_id.encode("utf-8") + str(
        sorted([p.model_dump() for p in predicates], key=str),
    ).encode("utf-8")
    signature = hmac.new(key, message, hashlib.sha256).hexdigest()

    token: dict[str, Any] = {
        "intent_id": intent_id,
        "signature": signature,
        "predicates": [p.model_dump() for p in predicates],
        "nbf": now - 5,
        "exp": now + 600,
        "iss": "equor",
        "aud": "axon",
        "capability": capability,
        "kid": kid,
        "debug_kid": kid,
    }
    if version:
        token["version"] = version
    if artifact_hash:
        token["artifact_hash"] = artifact_hash
    return token

def _alloc_budget_ms(estimate_ms: int, pool_ms: int) -> int:
    """
    Per-intent budget policy:
      - base = 1.2x estimate, floor 300ms
      - cap at 3000ms
      - cannot exceed current pool
    """
    base = max(300, int(estimate_ms * 1.2))
    return max(300, min(base, 3000, pool_ms if pool_ms > 0 else base))

# ----------------------------- Endpoints -------------------------------------

@route_router.post("/route")
async def route(
    event: AxonEvent,
    affect_override: AffectiveState | None = None,
    x_decision_id: str | None = Header(None, alias="X-Decision-Id"),
) -> dict[str, Any]:
    # simple pass-through wrapping for single events; forward header
    return await cognitive_cycle([event], affect_override, x_decision_id)

@route_router.post("/cognitive_cycle")
async def cognitive_cycle(
    events: list[AxonEvent],
    affect_override: AffectiveState | None = None,
    x_decision_id: str | None = Header(None, alias="X-Decision-Id"),
) -> dict[str, Any]:
    """
    Executes one full cognitive cycle (salience → planning → market → action),
    with Synapse policy/hints, KMS-signed caps, and SECL orchestration.
    """
    decision_id = x_decision_id or f"atune-dec-{uuid.uuid4().hex[:12]}"
    headers_common = {"x-decision-id": decision_id}
    REGISTRY.counter("atune.cycle.calls").inc()

    # Ingest follow-ups → micro-priors (best-effort)
    try:
        followup_ingest = harvest_batch_followups(
            [e.model_dump() if hasattr(e, "model_dump") else e for e in events],
        )
        REGISTRY.counter("atune.followups.ingested").inc(
            followup_ingest.action_results_ingested + followup_ingest.search_results_ingested,
        )
    except Exception:
        pass

    # Affect override / modulation
    if affect_override:
        affective_control_loop.update_state(affect_override)
    modulations = affective_control_loop.get_current_modulations()

    # === Budget from Synapse =================================================
    sc = SynapseClient()
    try:
        budget = await sc.get_budget(task_key="atune.policy")
        budget_manager.set_pool_ms_per_tick(int(budget.wall_ms_max))
        REGISTRY.gauge("atune.synapse.budget.wall_ms_max").set(int(budget.wall_ms_max))
    except Exception:
        REGISTRY.counter("atune.synapse.budget.fallback").inc()

    # Tempo reserves (Synapse hints)
    await apply_hinted_reserves(budget_manager, context={"num_events": len(events)})

    # Budget tick + tempo model
    budget_manager.tick()
    for ev in events:
        tempo_forecaster.observe_event(ev.event_type)
    tempo_forecaster.forecast_and_reserve(budget_manager)

    # === MAG gates (meta-attention) ==========================================
    avg_text_len = (
        float(
            np.mean([
                len(" ".join(e.parsed.get("text_blocks", []) if isinstance(e.parsed, dict) else []))
                for e in events
            ]),
        ) if events else 0.0
    )
    gating_vector = meta_attention_gater.get_gates(
        np.array([len(events), avg_text_len], dtype=np.float32),
        temperature=modulations.mag_temperature,
    )

    # === Synapse policy arm selection (fae/aife/hybrid) ======================
    try:
        sel = await sc.select_arm_simple(
            task_key="atune.policy",
            goal="Select Atune planning policy for this cycle",
            risk_level="normal",
            budget="normal",
            candidate_ids=["fae", "aife", "hybrid"],
        )
        policy_used = sel.champion_arm.arm_id
        synapse_episode_id = sel.episode_id
        market_strategy = getattr(sel, "market_strategy", None) or await resolve_market_strategy(
            context={"policy_arm": policy_used},
        )
        REGISTRY.counter("atune.synapse.select.success").inc()
    except Exception:
        policy_used = os.getenv("ATUNE_POLICY_FALLBACK", "fae")
        synapse_episode_id = f"fallback::{decision_id}"
        market_strategy = os.getenv("ATUNE_MARKET_STRATEGY", "vcg")
        REGISTRY.counter("atune.synapse.select.fallback").inc()

    # === Synapse hints: leak_gamma & per-head alpha ==========================
    try:
        hints_client = SynapseHintsClient()
        leak_hint = await hints_client.get_float(
            namespace="focus", key="leak_gamma", default=tuner.leak_gamma,
            context={"num_events": len(events), "avg_text_len": avg_text_len, "policy_arm": policy_used},
        )
        tuner.apply_hint(leak_hint)
        REGISTRY.gauge("atune.tuner.leak_gamma").set(tuner.leak_gamma)
    except Exception:
        REGISTRY.counter("atune.synapse.hint.leak_gamma.fail").inc()

    try:
        await apply_alpha_hints(
            per_head_conformal, default_alpha=0.05,
            context={"policy_arm": policy_used, "num_events": len(events)},
        )
    except Exception:
        REGISTRY.counter("atune.synapse.hint.alpha_per_head.fail").inc()
    alpha_val = getattr(per_head_conformal, "alpha", None)
    if isinstance(alpha_val, (int, float)):
        REGISTRY.gauge("atune.conformal.alpha.global").set(alpha_val)

    # === Bidding =============================================================
    bids: list[Bid] = []
    all_nodes: set = set()
    details: dict[str, Any] = {}
    per_head_pvals_accum: dict[str, float] = {}
    salience_snapshots: list[dict[str, Any]] = []

    # micro-priors from followups (best-effort)
    try:
        harvest_hints = salience_hints_from_harvest()
        top_kw = set((harvest_hints.get("top_keywords") or [])[:10])
        top_hosts = set((harvest_hints.get("top_hosts") or [])[:10])
    except Exception:
        top_kw, top_hosts = set(), set()

    for ev in events:
        # Canonicalize
        ce = canonicalizer.canonicalise(ev)

        # Schema priors
        try:
            main_text = ce.text_blocks[0] if ce.text_blocks else ev.event_type
            embedding = await get_embedding(main_text, task_type="RETRIEVAL_DOCUMENT")
        except Exception as e:
            embedding = np.zeros(3072, dtype=np.float32) # Fail safe to a zero vector
            details[ev.event_id] = {"status": "error_embedding", "detail": str(e)}

        matched_schema = memory_store.match_event_to_schema(embedding)

        salience_priors: dict[str, float] = dict((matched_schema.salience_priors or {}) if matched_schema else {})
        fae_priors: dict[str, float] = {}
        if matched_schema and getattr(matched_schema, "fae_utility_prior", None) is not None:
            fae_priors["utility"] = float(matched_schema.fae_utility_prior)

        # Micro-priors from harvested follow-ups
        try:
            text_blob = (" ".join(ce.text_blocks) if ce.text_blocks else "")[:2000].lower()
            if top_kw and any(kw in text_blob for kw in top_kw):
                salience_priors["novelty-head"] = float(salience_priors.get("novelty-head", 0.0)) + 0.02
            if top_hosts and isinstance(ev.source, str) and ev.source.lower() in {h.lower() for h in top_hosts}:
                salience_priors["keyword-head"] = float(salience_priors.get("keyword-head", 0.0)) + 0.02
        except Exception:
            pass

        # Run salience heads
        salience_scores = await salience_engine.run_heads(ce, gating_vector, priors=salience_priors)

        # Affect modulation on risk head
        if "risk-head" in salience_scores:
            salience_scores["risk-head"]["final_score"] *= modulations.risk_head_weight_multiplier

        # Conformal per head
        head_final: dict[str, float] = {k: float(v.get("final_score", 0.0)) for k, v in salience_scores.items()}
        for h, v in head_final.items():
            per_head_conformal.update(h, v)
        p_min, pvals = per_head_conformal.summary(head_final)
        per_head_pvals_accum.update(pvals)

        # Reflex pass (redact/block/flag)
        risk_details = salience_scores.get("risk-head", {}).get("details", {}) or {}
        reflex_rule = reflex_decide(risk_details)
        if reflex_rule:
            kind = reflex_rule["action"]
            if kind == "redact":
                apply_redactions(ev.parsed if isinstance(ev.parsed, dict) else {"parsed": ev.parsed},
                                 reflex_rule["fields"])
                details[ev.event_id] = {"status": "reflex_redacted",
                                        "rule": reflex_rule["matched"],
                                        "reason": reflex_rule["reason"]}
            else:
                details[ev.event_id] = {"status": f"reflex_{kind}",
                                        "rule": reflex_rule["matched"],
                                        "reason": reflex_rule["reason"]}
            REGISTRY.counter("atune.reflex." + kind).inc()
            if kind == "block":
                salience_snapshots.append({"event_id": ev.event_id, "scores": head_final, "pvals": pvals})
                continue

        # OOD salience → Unity escalation
        if p_min < per_head_conformal.alpha:
            details[ev.event_id] = {"status": "escalated_unity_salience", "pvals": pvals}
            try:
                http = await get_http_client()
                reason_obj = reason_conformal_ood(pvals, per_head_conformal.alpha)
                payload = build_escalation_payload(
                    episode_id=str(uuid.uuid4()),
                    reason=reason_obj,
                    decision_id=decision_id,
                    event_id=ev.event_id,
                    context={"stage": "salience_conformal"},
                )
                details[ev.event_id]["escalation_reason"] = reason_obj.model_dump()
                await http.post(
                    ENDPOINTS.ATUNE_ESCALATE,
                    json=payload,
                    headers={**headers_common, "x-budget-ms": "1000"},
                )
                secl_bump("escalations_salience", 1)
            except Exception:
                pass
            salience_snapshots.append({"event_id": ev.event_id, "scores": head_final, "pvals": pvals})
            continue

        # Deposit to salience field & plan
        all_nodes.add(ev.source)
        salience_field_manager.deposit([ev.source],
                                       sum(v.get("final_score", 0.0) for v in salience_scores.values()))
        summary = ce.text_blocks[0] if ce.text_blocks else "No content"

        # ⚠️ include decision_id for traceability in the planner
        deliberation_plan, _episode_id = await plan_deliberation(
            summary=summary,
            salience_scores=salience_scores,
            canonical_event=ce.model_dump(exclude={"original_event"}),
            decision_id=decision_id,
        )

        want_search = deliberation_plan.get("mode") == "enrich_with_search" and deliberation_plan.get("search_query")
        salience_snapshots.append({"event_id": ev.event_id,
                                   "scores": head_final,
                                   "pvals": pvals,
                                   "plan": deliberation_plan})

        if not want_search:
            details[ev.event_id] = {"status": "processed", "plan": deliberation_plan, "pvals": pvals}
            continue

        query = deliberation_plan["search_query"]
        base_intent = AxonIntent(
            intent_id="hypothetical",
            purpose=f"Hypothesis for event {ev.event_id}",
            target_capability="qora:search",
            params={"query": query},
            risk_tier="low",
            constraints={},
            policy_trace={},
            rollback_contract={},
        )

        probe_results = await probe_engine.run_probes(ce, priors=fae_priors)

        if policy_used in ("fae", "hybrid"):
            fae_score = fae_calculator.calculate_fae(salience_scores, probe_results)
            bids.append(Bid(
                source_event_id=ev.event_id,
                fae_score=fae_score,
                estimated_cost_ms=1500,
                action_details=base_intent,
            ))

        if policy_used in ("aife", "hybrid"):
            efe = active_inference_head.calculate_expected_free_energy(ce, "qora:search")
            efe_equiv = FAEScore(
                final_score=1000.0 - efe,
                terms={"efe": efe, "Risk": salience_scores.get("risk-head", {}).get("final_score", 0.0)},
            )
            bids.append(Bid(
                source_event_id=f"aife_{ev.event_id}",
                fae_score=efe_equiv,
                estimated_cost_ms=1500,
                action_details=base_intent,
            ))

        details[ev.event_id] = {"status": "processed", "plan": deliberation_plan, "pvals": pvals}

    # Salience diffusion (γ from Synapse)
    adj = await kg_interface.get_adjacency_list(list(all_nodes))
    salience_field_manager.run_diffusion_step(adj, leak_gamma=tuner.leak_gamma)
    hotspots = salience_field_manager.detect_hotspots()

    # === Cost-aware price hints from Synapse =================================
    try:
        price_per_cap = await HintsExtras().price_per_capability(context={"decision_id": decision_id})
        if isinstance(price_per_cap, dict) and bids:
            bids = scale_bid_costs(bids, price_per_cap)
    except Exception:
        pass

    # === Auction + Execute ====================================================
    winners = attention_market.run_auction(bids, budget_manager, strategy=market_strategy)
    secl_set_info("last_decision_id", decision_id)
    secl_set_gauge("last_winners_count", len(winners))
    http = await get_http_client()
    successes: list[int] = []
    total_cost_ms = 0

    known_caps = await get_known_capabilities()

    for idx, w in enumerate(winners):
        intent: AxonIntent = w.action_details
        real_id = str(uuid.uuid4())
        preds = [Predicate(variable="query", operator="len<=", value=500)]

        # Capability token
        token = _sign_token(real_id, preds, capability=intent.target_capability)

        # Finalize intent (pre-SECL)
        real_intent = intent.model_copy(update={
            "intent_id": real_id,
            "purpose": f"Enrich for {w.source_event_id}",
            "policy_trace": {"equor_cap_token": token},
        })

        # Compute per-intent budget from remaining pool
        pool_now = budget_manager.get_available_budget()
        x_budget = _alloc_budget_ms(int(w.estimated_cost_ms), pool_now)
        budget_manager.request_allocation(x_budget, source=f"atune_exec_{idx}")
        deadline_ts_ms = int(pytime.time() * 1000) + x_budget + 200

        # ====== SECL: gap detect / probecraft / playbook merge =================
        ev_id = w.source_event_id.replace("aife_", "")
        ev_snapshot = next((s for s in reversed(salience_snapshots) if s.get("event_id") == ev_id), None)
        head_pvals = (ev_snapshot or {}).get("pvals", {})
        trending_hosts = list(top_hosts) if top_hosts else []

        signals = SECLSignals(
            head_pvals=head_pvals,
            postcond_errors=[],
            regret_window=[],
            trending_hosts=trending_hosts,
            exemplars=[{"description": "search_query",
                        "payload": {"query": real_intent.params.get("query")}}],
            incumbent_driver=None,
        )

        headers_for_secl = {
            **headers_common,
            "x-budget-ms": str(x_budget),
            "x-deadline-ts": str(deadline_ts_ms),
        }

        # Prepare SECL adjustments
        proposed_intent_dict = real_intent.model_dump()
        final_intent_dict, secl_ctx = await prepare_intent_with_secl(
            decision_id=decision_id,
            intent={
                "capability": proposed_intent_dict.get("target_capability"),
                "constraints": proposed_intent_dict.get("constraints", {}),
            },
            known_capabilities=known_caps,
            signals=signals,
            headers=headers_for_secl,
        )
        if secl_ctx.get("secl", {}).get("gap_emitted"):
            secl_bump("gap_emitted", 1)

        # Merge SECL back
        real_intent_dict = proposed_intent_dict
        if "capability" in final_intent_dict and final_intent_dict["capability"]:
            real_intent_dict["target_capability"] = final_intent_dict["capability"]
        if "constraints" in final_intent_dict:
            real_intent_dict["constraints"] = final_intent_dict["constraints"]
        if "rollback_contract" in final_intent_dict:
            real_intent_dict["rollback_contract"] = final_intent_dict["rollback_contract"]
        real_intent_dict.setdefault("meta", {})["secl"] = secl_ctx

        # Execute on Axon
        try:
            r = await http.post(
                ENDPOINTS.AXON_ACT,
                json=real_intent_dict,
                headers={**headers_common, "x-budget-ms": str(x_budget), "x-deadline-ts": str(deadline_ts_ms)},
            )
            r.raise_for_status()
            out = r.json()
            rep_cost, delta_ms, delta_pct = audit_and_record(x_budget, out)
            details[w.source_event_id] = details.get(w.source_event_id, {})
            details[w.source_event_id]["cost_audit"] = {
                "allocated_ms": x_budget,
                "reported_ms": rep_cost,
                "delta_ms": delta_ms,
                "delta_pct": delta_pct,
            }
            details[w.source_event_id]["action_result"] = out
            ok = 1 if (isinstance(out, dict) and out.get("status") == "ok") else 0
            successes.append(ok)
            total_cost_ms += int(w.estimated_cost_ms)

            # ---- Optional A/B (Twin + Shadows) --------------------------------
            ab_enabled = os.getenv("ATUNE_AB_ENABLED", "1") == "1"
            ab_allow = int(os.getenv("ATUNE_AB_MAX_PER_CYCLE", "1")) > 0
            if ab_enabled and ab_allow and budget_manager.can_allocate_non_reserved(400):
                budget_manager.request_allocation(400, source="atune_ab")
                ab_req = dict(real_intent_dict)
                ab_req["intent_id"] = f"{real_intent_dict.get('intent_id')}::ab"
                try:
                    ab = await http.post(
                        ENDPOINTS.AXON_AB_RUN if hasattr(ENDPOINTS, "AXON_AB_RUN") else ENDPOINTS.AXON_AB,
                        json=ab_req,
                        headers={**headers_common, "x-budget-ms": "400"},
                    )
                    ab.raise_for_status()
                    ab_res = ab.json()  # { twin, shadows: [...] }
                    details[w.source_event_id]["ab_trial"] = ab_res
                    secl_bump("ab_trials", 1)

                    # Compute regret@compute
                    live_u = float((out.get("counterfactual_metrics") or {}).get("actual_utility", 0.0))
                    cand = [{"counterfactual_metrics": {"actual_utility": live_u}}]
                    if isinstance(ab_res.get("shadows"), list):
                        cand.extend(ab_res["shadows"])
                    best_u = _best_actual_utility(cand)
                    regret = max(0.0, best_u - live_u)
                    details[w.source_event_id]["ab_regret"] = {
                        "best_u": best_u,
                        "live_u": live_u,
                        "regret": regret,
                    }
                except Exception as e:
                    details[w.source_event_id]["ab_trial_error"] = str(e)
            # -------------------------------------------------------------------

        except Exception as e:
            details[w.source_event_id] = details.get(w.source_event_id, {})
            details[w.source_event_id]["action_result"] = {"status": "fail", "error": str(e)}
            successes.append(0)
            total_cost_ms += int(w.estimated_cost_ms)

    # === Report outcome to Synapse ===========================================
    try:
        success_rate = (sum(successes) / float(len(successes))) if successes else 0.0
        cost_norm = float(total_cost_ms) / float(max(1, budget_manager.pool_ms_per_tick))
        metrics: dict[str, Any] = {
            "ok": success_rate > 0.0,
            "success": success_rate,
            "cost_normalized": cost_norm,
            "pool_ms_per_tick": budget_manager.pool_ms_per_tick,
            "leak_gamma": tuner.leak_gamma,
        }
        # Regret aggregates
        try:
            regrets = []
            for _, info in (details or {}).items():
                rmeta = info.get("ab_regret")
                if rmeta and isinstance(rmeta.get("regret"), (int, float)):
                    regrets.append(float(rmeta["regret"]))
            if regrets:
                metrics["ab_regret_avg"] = float(sum(regrets) / len(regrets))
                metrics["ab_regret_max"] = max(regrets)
                metrics["ab_trials"] = len(regrets)
        except Exception:
            pass

        await sc.log_outcome(
            episode_id=synapse_episode_id,
            task_key="atune.policy",
            metrics=metrics,
            simulator_prediction=None,
        )
        REGISTRY.counter("atune.synapse.log_outcome").inc()
    except Exception:
        REGISTRY.counter("atune.synapse.log_outcome.fail").inc()

    # === WhyTrace + ReplayCapsule ============================================
    try:
        salience_summary = {
            "per_head_alpha": {"default": per_head_conformal.alpha},
            "last_pvals": per_head_pvals_accum,
            "snapshots": salience_snapshots[-min(5, len(salience_snapshots)) :],
        }

        market_summary = {
            "strategy": market_strategy,
            "bids": [{
                "source_event_id": b.source_event_id,
                "score": getattr(b.fae_score, "final_score", None),
                "est_cost_ms": b.estimated_cost_ms,
                "capability": getattr(b.action_details, "target_capability", None),
            } for b in bids[:10]],
            "winners": [{
                "source_event_id": w.source_event_id,
                "score": getattr(w.fae_score, "final_score", None),
                "est_cost_ms": w.estimated_cost_ms,
                "capability": getattr(w.action_details, "target_capability", None),
            } for w in winners],
        }

        if str(market_strategy) == "pareto_knee":
            try:
                market_summary.update(summarize_pareto_knee(bids, winners))
            except Exception:
                pass

        verdicts = {
            "winners": [w.source_event_id for w in winners],
            "ab_trials": sum(1 for v in details.values() if "ab_trial" in v),
            "escalations": [
                {"event_id": k, **v.get("escalation_reason", {})}
                for k, v in details.items() if "escalation_reason" in v
            ],
            "cost_audits": [
                {"event_id": k, **v.get("cost_audit", {})}
                for k, v in details.items() if "cost_audit" in v
            ],
        }

        why = WhyTrace(
            decision_id=decision_id,
            salience=salience_summary,
            fae_terms={},  # optional aggregation
            probes={},      # optional
            verdicts=verdicts,
            market=market_summary,
            created_utc=datetime.now(UTC).isoformat(),
        )

        capsule = ReplayCapsule(
            decision_id=decision_id,
            inputs={"events": [e.model_dump() for e in events]},
            versions={"engine": "atune-v1"},
            timings={"pool_ms_per_tick": budget_manager.pool_ms_per_tick},
            env={
                "embedding_dim": 3072,
                "alpha": per_head_conformal.alpha,
                "flags": {"ab": os.getenv("ATUNE_AB_ENABLED", "1"),
                          "market": os.getenv("ATUNE_MARKET_STRATEGY", "vcg")},
            },
            hashes={},
            created_utc=datetime.now(UTC).isoformat(),
        )
        try:
            capsule.inputs["ab"] = {
                k: {"ab_trial": v.get("ab_trial"), "ab_regret": v.get("ab_regret")}
                for k, v in details.items()
                if "ab_trial" in v or "ab_regret" in v
            }
        except Exception:
            pass

        barcodes = record(decision_id, why, capsule)
    except Exception:
        barcodes = {}

    return {
        "decision_id": decision_id,
        "cycle_summary": {
            "decision_id": decision_id,  # echo for tracing UIs
            "actions_executed": len(winners),
            "field_hotspots": hotspots,
            **barcodes,
        },
        "event_details": details,
    }
