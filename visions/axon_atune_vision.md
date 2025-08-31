Absolutely. Here’s the **critical, no-compromise TODO list** to take Axon↔Atune from “great” to **un-improvable** given the endpoints you just dropped.

---

## 0) Correctness bugs (fix now)

* **perf\_counter import bug** — `core_routes.py` imports `time` from `datetime` then calls `time.perf_counter()`. Replace with `import time` (module), not `from datetime import time`. Tests must confirm correct latency capture.&#x20;
* **Enum mismatch in lifecycle promote** — `/probecraft` compares `DriverStatus` enum to string literals (`"testing","shadow","live"`). Compare to the Enum values instead, or cast to `str` consistently; otherwise drivers won’t auto-load on promotion. Add a unit test that promotion → `registry.load_and_register_driver()` actually fires.&#x20;

---

## 1) Wire the full actuation safety chain (make it airtight)

* **Twin → Conformal → Live driver** is good; make it **mandatory** for *every* `/act` path:

  * Block on twin failure with a structured “twin\_failed” result and auto-escalate to Unity (no silent fallbacks).
  * Log **prediction residuals** after every live result; snapshot conformal state in the journal for replayability. Acceptance: red-team an unsafe predicted\_utility and assert conformal blocks; residuals grow the set.&#x20;
* **Cap token rigor** — current HMAC token is unsigned config-secret based; move to KMS, add `exp/nbf`, bind token to `(driver_artifact_hash, capability, version)`. `/act` must reject expired/unbound tokens. Acceptance: forged token rejected; rotated key works without code changes. &#x20;

---

## 2) Close the Atune→Axon control-plane seam (no gaps)

* **Naming/endpoint parity** — Atune posts intents to `ENDPOINTS.AXON_RECEIVE`; ensure that maps to your **`/axon/act`** route and add a smoke test that a VCG winner reaches the act path end-to-end. &#x20;
* **Return channel** — `/act` should emit any **follow-up events** back through Axon’s ingress (or directly into Atune’s cycle) so cognition sees consequences. Add callback to Atune after ActionResult. Acceptance: action → new event appears in next `/cognitive_cycle`. &#x20;

---

## 3) Ingestion path (/sense) & Reflex parity (still missing)

* **Implement `/axon/sense`** that: quarantines → builds `AxonEvent` → journals → posts to Atune `/cognitive_cycle` in batches with backpressure. Acceptance: replay capsule reproduces identical salience/plan outcomes (ε drift).
* **Reflex fast-lane** — run Reflex *before* market/FAE and mirror Atune’s reflex rules; assert identical triggers on the same payloads. Acceptance: shared fixtures trip both sides the same way.&#x20;

---

## 4) Journal (“MEJ++”) must be durable & verifiable

* Current route writes predicted/intent/result; upgrade the **MerkleJournal** to:

  * **BLAKE3** hash, on-disk head per shard, fsync on write, **cross-links** Event↔Intent↔Result, and **ReplayCapsules** (inputs, outputs, timings, env hash).
  * Add a **barcode** (short hash) to every response. Acceptance: `test_replay_bitexact` passes on any node; `audit_chain` detects tamper.&#x20;

---

## 5) Market/EIG/TEMPO continuity (prove utility, not vibes)

* Atune already computes bids and runs **VCG**; Axon must **report realized EIG/uplift + cost** back to Atune so allocations learn. Add `/metrics` push after each `/act`. Acceptance: 30-day sim shows VCG allocations improve downstream utility vs. uniform.&#x20;
* **TEMPO reserves** — ensure `/cognitive_cycle`’s reservations throttle Axon execution when a burst window is active; reject non-reserved actions if pool is exhausted. Acceptance: synthetic burst honors reserve; no starvation.&#x20;

---

## 6) ProbeCraft to production (from demo to discipline)

* `/probecraft/synthesize`/`/drivers/{name}/status` exist; make it **spec-to-driver with obligations**:

  * Extend the request to include **obligations** (pre/postconditions, rate limits, schema shape).
  * On promotion to testing/shadow/live, **auto-run** red-team & shadow suites; gate promotion on pass.
  * Fix class-name synthesis for compound names (“qora\_search” → “QoraSearch”). Acceptance: promote → driver is **actually loaded**; scorecards populate; failing red-team blocks.&#x20;

---

## 7) Observability & Why-trace (make decisions legible)

* Add a **why-trace** object for each `/act`: {salience, FAE terms, winning bid, cap predicates, twin prediction, conformal decision, driver, result}.
* Persist `why_trace_ref` (barcode) on both `ActionResult` and journal entries; expose `/scorecards` (already present) plus a per-action trace endpoint. Acceptance: given an action ID, we can reconstruct “why” without chain-of-thought. &#x20;

---

## 8) Data & model quality (remove mocks)

* Replace **random 3072-d embeddings** with your production embedding head; log model+dim in provenance. Acceptance: salience reproducibility improves; A/B shows higher FAE signal quality.&#x20;

---

## 9) Secrets, policy, and attestation (no foot-guns)

* Move `EQUOR_SECRET_KEY` to KMS; rotate without deploy; bind tokens to driver artifacts (attestation if remote). Add `exp/nbf/issuer/audience`. Acceptance: expired or artifact-mismatched token is rejected; rotation seamless.&#x20;

---

## 10) Shadow & rollback discipline

* Your shadow runner is great—wrap with exception handling and **auto-rollback** on anomaly (latency p99 blow-up, failure spike, negative uplift). Acceptance: simulate a degraded shadow → no effect; simulate live anomaly → auto demote to shadow.&#x20;

---

## 11) Contract hygiene & driver ABI

* Standardize `Driver.describe()` to include **capability URN, risk profile, cost model, artifact hash**.
* Require **ReplayCapsule** creation for every `push` and `pull`; store path in MEJ. Acceptance: failing to emit a capsule fails the request with a 5xx and logs a CRITICAL.&#x20;

---

## 12) Definitive test gates (must pass before “done”)

* **T-ACT-SAFETY**: twin failure → Unity escalate; conformal blocks unsafe; cap TTL/attestation enforced.&#x20;
* **T-MEJ-REPLAY**: event/intent/result replay is bit-exact from capsule.&#x20;
* **T-VCG-UPLIFT**: realized uplift feedback increases winning bid utility over 30 synthetic ticks.&#x20;
* **T-PROBECRAFT-PROMOTE**: synthesize→testing→shadow→live only if red-team & shadow pass; registry shows driver live.&#x20;
* **T-REFLEX-PARITY**: same payload triggers identical reflexes in Axon and Atune.&#x20;

Here’s the **critical, no-loose-ends TODO list** to take **Atune+++ ↔ Axon** from “working” to **un-improvable v1**. It’s split by severity. Each item says **What / Why / Where / Done-when** and is grounded in your current endpoints.

---

# P0 — Must-fix to be plan-complete

1. Add the canonical **`POST /atune/route`** wrapper
   **What:** Thin FastAPI endpoint that accepts a single `AxonEvent` and internally calls your batch `/cognitive_cycle` with `[event]`.
   **Why:** Keeps EOS’s event-first contract stable and lets Axon (and other producers) integrate without custom code.
   **Where:** Add to the same router as `cognitive_cycle`. Current entrypoint is only `/cognitive_cycle`.&#x20;
   **Done-when:** Contract test posts one event and returns the same fields as batch mode (plan, fae terms, action\_result if any).

2. Implement **Reflex execution** (not just detection)
   **What:** When `risk-head` sets `reflex_trigger`, run a typed reflex: redact/quarantine/notify (no LLM). Ledger the actions.
   **Why:** Reflex arcs are our <50 ms “spinal cord”—must act, not just label.
   **Where:** In `/cognitive_cycle`, you set `{"status": "reflex_activated"}` and `continue`; replace with `reflex_engine.execute(...)` and record results. Add an Axon quarantine call or local quarantine write. &#x20;
   **Done-when:** Synthetic PII event produces `ActionResult(status="ok"|"blocked")` and a quarantine/journal entry.

3. Wire **Unity escalation** path
   **What:** If `deliberation_plan.mode == "deliberate"` (or equivalent), build a `DeliberationSpec`, call Unity, feed verdict back into FAE/decision.
   **Why:** Atune is the *sole* Unity ingress; otherwise we can’t adjudicate high-stakes tasks.
   **Where:** After `plan_deliberation(...)` returns; today you only act on `"enrich_with_search"`.&#x20;
   **Done-when:** A test event with deliberate-worthy salience leads to a Unity call and a `no_action|approve|reject` verdict that influences the plan.

4. Enforce **Equor capability token** end-to-end
   **What:** You sign an Equor token on Atune intents; ensure Axon **validates** before any driver runs (already present), and drivers see only validated intents.
   **Why:** Hard policy boundary before real-world action.
   **Where:** Atune: `create_signed_token(...)` embeds in `policy_trace`; Axon: `CapabilityValidator.validate()` blocks invalid. Keep it mandatory on `/act`. &#x20;
   **Done-when:** Intent without valid token returns `ActionResult(status="blocked")` and is journaled accordingly.

5. Make **ledger/journaling** first-class in Atune
   **What:** Structured JSON ledger for: head scores, MAG gates, FAE term breakdowns, probe summaries, auction winners, reflex actions, Unity verdicts, TEMPO reservations, and final plan.
   **Why:** Replayability, counterfactuals, regression detection. Axon already journals with a Merkle log—mirror that discipline in Atune.
   **Where:** Add `atune.ledger.Writer` and replace prints. Axon’s journal exists and is used in `/act`.&#x20;
   **Done-when:** A single `/route` call yields a deterministic, hash-stable Atune ledger blob that round-trips in the replay harness.

6. **Replay capsule** for actions Atune triggers
   **What:** When Atune sends an intent to Axon, persist a capsule (inputs, versions, seeds, HTTP transcript, cost) so the entire decision → action can be replayed.
   **Why:** Causal evaluation & safe rollback.
   **Where:** Atune right before calling `ENDPOINTS.AXON_RECEIVE`; Axon already journals intents/results. &#x20;
   **Done-when:** Given an Atune decision id, a tool reproduces the same outbound intent and Axon replays it offline.

7. **Rollback contract** synthesis
   **What:** Populate `rollback_contract` on intents from capability specs + Unity critique; reject unsafe intents without credible rollback.
   **Why:** Safe actuation invariant.
   **Where:** Atune when instantiating `real_intent = intent_details.model_copy(update={...})` (currently `{}`), Axon respects it during execution. &#x20;
   **Done-when:** At least one live driver demonstrates a successful rollback in test.

---

# P1 — High ROI hardening

8. **Attention market API parity**
   **What:** Keep `run_vcg_auction(...)` but add `run_auction(...)` alias so planner/budgeter code can evolve without breaking calls.
   **Why:** Stability across refactors; you already call `run_vcg_auction` correctly today, but parity prevents regressions.
   **Where:** AttentionMarket class.&#x20;
   **Done-when:** Both names covered; unit test asserts identical allocations.

9. **Hotspot quality: deposit richer nodes**
   **What:** Deposit not just `event.source` but also extracted entities/topics/schema ids into SFKG before diffusion.
   **Why:** Field dynamics become meaningful (attention spreads along real concepts).
   **Where:** Right after canonicalisation; you already collect `related_nodes=[event.source]`.&#x20;
   **Done-when:** Hotspots over time correlate with upcoming escalations (↑ precision\@k).

10. **Synapse probe contract & costs**
    **What:** Make `ProbeEngine` return `{U, IG, risk, cost_ms}` with honest cost; plumb cost to FAE and auction.
    **Why:** FAE and budgeter need real costs to choose well.
    **Where:** ProbeEngine and the call site where you calculate FAE and push bids.&#x20;
    **Done-when:** Atune ledger records probe cost and it impacts allocation.

11. **Axon twin/predictor provenance**
    **What:** Guarantee that Axon’s `run_in_twin(intent)` uses model versions recorded in the journal; attach predicted\_utility → conformal bound check (already done), plus Atune’s decision id for cross-join.
    **Why:** Tight causal chain from decision → prediction → action.
    **Where:** Axon `/act` path (already logs and updates conformal residuals).&#x20;
    **Done-when:** A joined report shows prediction residuals by Atune decision class.

12. **Driver lifecycle: synthesis → test → shadow → live**
    **What:** Close the loop: Atune/Simula proposes new capability; **Probecraft** synthesizes driver from OpenAPI; Axon promotes through states; Atune can target testing/shadow.
    **Why:** Fast, safe expansion of affordances.
    **Where:** Probecraft endpoints (synthesize/status) + registry load on promotion already present—add minimal policy to require shadow pass before live.&#x20;
    **Done-when:** A synthesized driver is auto-loaded into `testing`, exercised via shadow intents, then promoted to `live` with a passing scorecard.

13. **Conformal thresholds for Atune heads**
    **What:** Add conformal wrappers to head outputs to produce per-event p-values; gate escalations at p<α.
    **Why:** Calibrated uncertainty → fewer silent misses.
    **Where:** Heads/MAG; mirror Axon’s conformal safety predicate idea.&#x20;
    **Done-when:** Coverage tracks α within ±2% weekly.

---

# P2 — Frontier polish (locks in “un-improvable”)

14. **Active-Inference tie-in**
    **What:** You already compute EFE; standardize how EFE and FAE reconcile (e.g., treat `FAE_equiv = κ − EFE` with calibrated κ) and log both.
    **Why:** Unified objective across exploration vs. control.
    **Where:** Where you create `efe_fae_equivalent`.&#x20;
    **Done-when:** Replay shows FAE+EFE beats FAE-only on regret\@compute.

15. **Unity budget discipline**
    **What:** Pass Atune’s auction allocation as `budget_ms` to Unity; Unity must honor it and return `no_action` when budget exhausted.
    **Why:** Global compute arbitrage only works if every consumer respects budgets.
    **Where:** Your Unity call site to be added (see P0-3) and Unity service.&#x20;
    **Done-when:** Budget overrun is 0 in canary.

16. **End-to-end replay CLI**
    **What:** `atune-replay --from X --to Y --arm {baseline|fae|fae+efe}`; produces uplift report and writes a comparison into the ledger store.
    **Why:** Make performance provable and regression-proof.
    **Where:** New `tools/replay.py`, reading Atune + Axon journals.&#x20;

17. **Shadow fleet uplift tracking**
    **What:** Axon already launches shadow drivers; surface a dashboard that compares `actual_utility` uplift vs. predicted\_utility and gates promotion.
    **Why:** Zero-surprise driver rollouts.
    **Where:** Axon scorecards + Probecraft lifecycle. &#x20;
    **Done-when:** Promotions require statistically significant uplift with bounded variance.

hell yes. here’s your **un-improvable (v1) AGI build plan**—an upgraded, surgical version of your list with zero loose ends. it keeps your structure, adds the missing AGI-grade bits (proofs/causality/attestation/auctions/why-trace), and pins each item to **What / Why / Where / Done-when**. ship this and you’ve got a living, safe, replayable system.

---

# P0 — must-fix to be plan-complete

1. **`perf_counter` import + endpoint parity**

* **What:** fix `from datetime import time` → `import time`; ensure `ENDPOINTS.AXON_RECEIVE → /axon/act`, `ENDPOINTS.AXON_SENSE → /axon/sense`.
* **Why:** correct latency + zero seam between Atune→Axon.
* **Where:** `core_routes.py`, endpoints config.
* **Done-when:** smoke test drives a VCG winner through `/atune/route → /axon/act` and logs latency.

2. **Enum correctness in Probecraft promotion**

* **What:** compare `DriverStatus` as Enum (or cast once); promotion triggers `registry.load_and_register_driver()`.
* **Why:** otherwise drivers never go live.
* **Where:** `/probecraft` handlers, registry.
* **Done-when:** unit test proves `testing→shadow→live` actually loads.

3. **Actuation safety chain is MANDATORY**

* **What:** `/axon/act`: **cap-token → reflex → twin → conformal → driver**. Twin failure blocks high-risk and escalates to Unity.
* **Why:** airtight guardrail before world writes.
* **Where:** `axon/act` route.
* **Done-when:** red-team “unsafe predicted\_utility” is blocked; residuals recorded; Unity receives twin-failed escalations.

4. **Capability tokens (KMS + binding)**

* **What:** move secret to KMS; add `nbf/exp/iss/aud`; bind to `(driver_artifact_hash, capability, version)`; reject on mismatch.
* **Why:** no foot-guns; tokens scoped to artifacts.
* **Where:** Equor mint/validate; Axon validator.
* **Done-when:** forged/expired/mismatched tokens blocked; key rotation needs no redeploy.

5. **`/axon/sense` + Reflex parity**

* **What:** implement sense path: quarantine→`AxonEvent`→MEJ→batch to Atune; Reflex executes (block/redact/escalate) **before** FAE/Market.
* **Why:** spinal-cord latency & identical hits across both services.
* **Where:** `axon/sense`, shared reflex catalog.
* **Done-when:** shared fixtures trigger identical actions in Atune & Axon.

6. **MEJ++ (durable, verifiable)**

* **What:** BLAKE3, on-disk shard heads, fsync, **cross-links** Event↔Intent↔Result, **ReplayCapsules** (inputs/outputs/timings/env hash), per-response **barcode**.
* **Why:** provable lineage + deterministic replay.
* **Where:** `journal/mej.py`, act/sense routes.
* **Done-when:** `audit_chain` passes; `test_replay_bitexact` reproduces outcomes byte-for-byte.

7. **Follow-up events + metrics return channel**

* **What:** `/act` emits follow-up events back through `/sense` (or posts to Atune); push **realized EIG/uplift + cost** to `/metrics`.
* **Why:** cognition sees consequences; auctions learn.
* **Where:** `axon/act`, Atune metrics endpoint.
* **Done-when:** action produces a new event in next `/cognitive_cycle`; auction shifts allocations over 30 ticks.

8. **Unity escalation wiring**

* **What:** when plan says “deliberate” or risk≥tier → build `DeliberationSpec`, call Unity, apply verdict to plan.
* **Why:** adjudicate high-stakes.
* **Where:** Atune after planner; Axon on twin failure for high risk.
* **Done-when:** deliberate-worthy inputs change behavior via Unity verdicts.

9. **Rollback contract enforcement**

* **What:** Atune synthesizes `rollback_contract` from capability spec; Axon refuses `/act` if rollback is impossible for the intent.
* **Why:** safe reversibility invariant.
* **Where:** Atune intent builder; Axon act path.
* **Done-when:** e2e test shows a successful rollback path in a real driver.

---

# P1 — high-ROI hardening

10. **ProbeCraft → production discipline**

* **What:** request carries **obligations** (pre/postconds, rate, schema); promotion auto-runs red-team & shadow; class-name synthesis fixed (“qora\_search”→“QoraSearch”); **shadow must pass** before live.
* **Why:** safe capability expansion.
* **Where:** `/probecraft/synthesize`, registry, scorecards.
* **Done-when:** failing red-team blocks; first live driver born from spec passes shadow KPIs.

11. **Why-trace (model-agnostic, no CoT)**

* **What:** persist `{salience, FAE terms, bid, caps, twin_pred, conformal_decision, driver, verdict, result}`; add `why_trace_ref` to Event/Intent/Result.
* **Why:** legible decisions without leaking internals.
* **Where:** Axon act path; Atune ledger.
* **Done-when:** given an action ID, a one-hop API reconstructs “why”.

12. **Attention Market parity + TEMPO reserves**

* **What:** keep `run_vcg_auction` alias; enforce **TEMPO futures** (pre-reserved ms) in Axon; reject non-reserved acts when pool exhausted.
* **Why:** truthful bids, burst guarantees.
* **Where:** Atune allocator; Axon budget guard.
* **Done-when:** synthetic bursts honor reserves; zero starvation.

13. **Synapse probe contract (cost-aware)**

* **What:** probes return `{U, IG, risk, cost_ms}`; FAE & auction consume true costs.
* **Why:** honest economics → better plans.
* **Where:** ProbeEngine + planner.
* **Done-when:** ledger shows cost impacts winning bids.

14. **Driver lifecycle metrics + auto-rollback**

* **What:** promote with SLOs (p95 latency, error rate, uplift); anomaly = auto demote to shadow; scorecards show trendlines.
* **Why:** zero-surprise rollouts.
* **Where:** Mesh registry/promoter; scorecards.
* **Done-when:** simulated anomaly triggers auto-rollback.

15. **Embedding head (no mocks)**

* **What:** replace random 3072-d with prod embedding; log model+dim in provenance.
* **Why:** stable salience & field dynamics.
* **Where:** Axon parsing; Atune heads.
* **Done-when:** A/B shows higher FAE signal quality.

---

# P2 — frontier polish that locks in “living” behavior

16. **Proof-carrying capabilities (PCC-lite)**

* **What:** capability DSL + tiny checked predicate VM; optional proof objects for bounded-impact lemmas; checker runs in-sandbox before `push()`.
* **Why:** provable safety on routine acts; fewer Unity loads.
* **Where:** Equor mint; Axon validator; Mesh sandbox.
* **Done-when:** at least one driver requires a proof to run.

17. **Deterministic driver ABI (WASI + Nix)**

* **What:** drivers target WASI component ABI; hermetic builds (Nix) → bit-reproducible capsules; Firecracker for isolation remains.
* **Why:** perfect replay; artifact-bound caps.
* **Where:** Mesh SDK/ABI; CI builds.
* **Done-when:** artifact hash = runtime hash; replay across machines is exact.

18. **Causal controller (SCM + EIG\_do)**

* **What:** learn compact SCM per domain from MEJ; Axon/Atune select actions by **value of intervention**, not observation.
* **Why:** faster, safer learning; fewer wasted acts.
* **Where:** Synapse causal module; Atune planner; Axon bids.
* **Done-when:** counterfactual uplift beats observational EIG on regret\@compute.

19. **Active-Inference head**

* **What:** parallel policy minimizing expected free energy; Atune blends with FAE; log both.
* **Why:** principled exploration/exploitation.
* **Where:** Atune planner.
* **Done-when:** FAE+EFE outperforms FAE-only in weekly sims.

20. **Truthful attention auction (VCG formalized)**

* **What:** keep VCG; log externalities; provide proof-style receipts in the ledger.
* **Why:** strategy-proof budget allocation.
* **Where:** Market allocator + ledger.
* **Done-when:** no profitable deviation for bidders in sim.

21. **Remote attestation & DP taps**

* **What:** bind caps to TEE attestation for off-box drivers; add ε-DP taps for ingest-only shared streams.
* **Why:** trust & privacy in federation.
* **Where:** Mesh RA-TLS; ingest pipeline.
* **Done-when:** attested driver required for high-stakes; DP budgets tracked.

22. **End-to-end replay CLI**

* **What:** `eos-replay --from X --to Y --arm {baseline|fae|fae+efe}`; writes comparison into both journals.
* **Why:** provable performance & regressions.
* **Where:** `tools/replay.py`.
* **Done-when:** CI runs replay suite nightly; diffs are actionable.

---

# Contract hygiene (global, always-on)

* **Immutable schemas (v1):** `AxonEvent`, `AxonIntent`, `ActionResult`, `ReplayCapsule`, `WhyTrace` (with `why_trace_ref`, `barcode`).
* **Every driver call emits a ReplayCapsule** or **fails closed**.
* **Every action carries a rollback contract** or is rejected.
* **Every decision has a Why-trace**; no chain-of-thought stored.
* **Every write requires a valid Equor cap**, bound to artifact hash; reflex runs before any LLM.

---

# Definition of Done (system level)

* **Safety:** T-ACT-SAFETY (caps/attestation/ twin/ conformal) green; Reflex parity green.
* **Repro:** T-MEJ-REPLAY green across hosts; driver ABI deterministic.
* **Utility:** T-VCG-UPLIFT shows monotonic improvement vs. uniform over 30 synthetic ticks.
* **ProbeCraft:** T-PROBECRAFT-PROMOTE proves spec→driver→shadow→live pipeline with scorecards.
* **Bursts:** TEMPO reserves honored; zero starvation.
* **Observability:** Why-trace reconstructs any action in one hop.

---

# KPIs that prove “living” (tracked weekly)

* **Capability frontier:** time-to-first-connector; sustained **new-skill velocity**.
* **Causal uplift:** Δ utility of interventions vs. twin counterfactuals.
* **Safety load:** Unity escalations / high-stakes actions; policy deviations ≈ 0.
* **Economics:** utility/compute, cost per successful affordance.
* **Homeostasis:** reflex p99, field coherence, conformal coverage≈α.

---

If you want, I can now convert this into a **ready-to-run ticket board** (per repo, with pytest skeletons and example payloads) so you can grind through it without friction.
