

# Cross-System Requirements Triggered by Atune+++

Atune+++ adds: **FAE** (free-attention energy), **MAG** (meta-attention gating), **SFKG** (salience field), **Reflex Arcs**, **TEMPO** forecasting, **Attention Market**, probes, conformal thresholds, and (optionally) Pareto FAE. The items below are *must-own* for peer services.

---

## 1) Synapse (learning, critics, orchestration)

### New/updated responsibilities

* **Small-arm probes**: fast predictors for `{U, IG, Risk, Cost}` used by Atune’s micro-sims.
* **Outcome critics**: train/evolve models that predict downstream reward deltas and risk; nightly **episodic→parametric distillation** for ms-latency queries.
* **Mode params**: serve per-mode λ (epi/risk/cost) and MAG temperature; expose regret/uncertainty to condition Atune.
* **Embedding service**: deterministic 3072-d embeddings (pin model+version); streaming availability to Atune.
* **Conformal wrappers**: per-head calibration sets for p-values and coverage monitoring.
* **Cost model**: ms/\$ estimates for typical actions (`light_analyze`, `deliberate`, `enqueue`, etc.), updated from telemetry.

### API contracts (JSON; hard timeouts)

* `POST /synapse/probe` (≤80ms p95)

```json
{ "event": {...}, "action": {"kind":"light_analyze|deliberate|enqueue|discard"}, "context": {"focus_ids":[...], "risk":0.0, "novelty":0.0} }
→ { "U":0.0, "IG":0.0, "risk":0.0, "cost_ms":42, "sens": {"dU_drisk":0.0, "dU_dnovelty":0.0} }
```

* `POST /synapse/embeddings` (≤40ms p95 per chunk)

```json
{ "texts":["..."], "version":"text-embed-x.y" } → { "vectors":[[...]], "dim":3072, "version":"..." }
```

* `GET /synapse/mode_params?mode=default` (≤10ms)

```json
{ "lambdas":{"epi":0.8,"risk":1.1,"cost":0.6}, "mag_temp":1.0, "timestamp":... }
```

* `POST /synapse/conformal/calibrate` (offline/batch) → coverage report for heads.

### SLAs / monitors

* Probe p95 ≤ 80ms; coverage within ±2% of α; drift alarm on critics ≤ 15min MTTR.

### Tests you own

* Replay A/B: prove probe-augmented FAE reduces regret\@compute ≥15% on last 7 days.
* Conformal coverage test per head; fail build if |coverage−α|>0.03.

---

## 2) Unity (deliberation & adjudication)

### Responsibilities

* **Single ingress** from Atune with `DeliberationSpec`; choose protocol (Debate, Critique-Repair, Mixture).
* Return **verdict class** (`approve|reject|info_needed|no_action`) and **witnessed claims** (schema-bound).
* Accept **budget/deadline** constraints from Atune; stream transcript hash for Atune’s ledger.

### API contract

* `POST /unity/escalate` (budget-aware)

```json
{ "topic":"...", "stakes":"...", "focus_context":[...], "protocol":"auto|debate|critique_repair",
  "budget_ms": 30000, "deadline_ts": 169..., "claims":[{"text":"...", "confidence":0.62}] }
→ { "verdict":"approve|reject|no_action|info_needed",
     "adjudication":{"summary":"...", "confidence":0.73},
     "transcript_hash":"...", "witness":[{"claim":"...", "support":[{"src":"...", "weight":0.8}]}] }
```

### SLAs / monitors

* p95 time ≤ budget; **no\_action** label rate tracked (Atune uses it as false-escalation signal).
* Protocol selection accuracy vs. oracle tags ≥ 0.7.

### Tests

* Contract tests with Atune replay logs; determinism under fixed seeds.

---

## 3) Equor (identity, constitution, affect)

### Responsibilities

* **Affect vector** producer (curiosity, caution, integrity load, fatigue, etc.) at 1–5Hz to modulate MAG/FAE.
* **Risk clamps & domain watchlists** for reflex rules and FAE risk penalty.
* **Constitutional checkpoints**: sign-off gates for high-impact plans (budget > X, domain ∈ protected).

### API contracts

* `GET /equor/affect` → `{ "curiosity":0.5,"caution":0.4,"integrity":0.7,"fatigue":0.1,"ts":... }`
* `GET /equor/rules/reflex` → reflex domain thresholds & keywords.
* `POST /equor/checkpoint` with Plan preview → `{ "approved":true, "notes":"..." }`

### SLAs / monitors

* Affect freshness < 2s; checkpoint response ≤ 100ms for cached policies.

### Tests

* Clamp application property test: risk floor applied in Atune ledger when domain triggers.

---

## 4) Qora (memory & knowledge)

### Responsibilities

* **Bi-modal store**: each accepted claim saved as vector + symbolic triple with provenance & timestamp.
* **Source reliability**: maintain trust scores for coherence head; serve them to Atune.
* **Belief revision**: if Atune’s controversy head or Unity flags contradictions, Qora opens a re-check task and deprecates confidence pending review.

### API contracts

* `POST /qora/claims` → `{ "id":"...", "triple":["subj","pred","obj"], "embedding":[...], "prov":{"src":"...","ts":...} }`
* `GET /qora/source_reliability?src=...` → `{ "reliability":0.73, "n":1243, "last_ts":... }`
* `POST /qora/contradiction` → opens ticket, returns handle.

### SLAs / monitors

* Claim write p95 ≤ 30ms; reliability cache hit rate ≥ 95%.

### Tests

* Coherence A/B: trusted-weighted corroboration lowers false-escalation without recall loss.

---

## 5) Axon (ingestion)

### Responsibilities

* **CanonicalEvent enrichment**: ensure `event_type`, `source`, `timestamp`, **typed numerical\_features**, and **stable IDs**.
* **Embeddings precompute** (optional): co-locate embedder near Axon to reduce latency; version pin.
* **Pre-redaction** for sensitive data prior to persistence; emit PII flags to help Atune reflexes.
* **Source metadata**: provide initial trust priors and rate-limit hints.

### Contract alignment

* Must produce exactly the event shape Atune expects; include `meta.source_auth`, `meta.tenant`, and `meta.privacy_tags` where possible.

### SLAs / monitors

* Event delivery jitter < 200ms p95; embedding backfill success > 99.5%.

### Tests

* Schema validator on Axon output; redaction conformance tests.

---

## 6) Simula (codegen & patching)

### Responsibilities

* **Self-evolution specs intake** from Atune error mining (missed criticals, slow verdicts, blind spots).
* **Tool discovery loop** for Atune: implement missing analyzers, parsers, cheap verifiers; ship as minimal adapters with tests.
* **Evaluator suites**: Atune heads have micro-benchmarks (pAUC\@k, coverage, drift), run in CI.

### API contracts

* `POST /simula/propose_patch` with spec → returns candidate IDs, diffs, and test coverage.
* `POST /simula/eval/atune_heads` → returns benchmark metrics for heads/gates.

### SLAs / monitors

* Median time from spec→passing patch ≤ 6h; eval runtime ≤ 10min per suite.

### Tests

* Golden-set regression for heads; patch rollback path validated.

---

## 7) Evo (self-evolution pipeline)

### Responsibilities

* **Gate & apply** Atune component updates (heads/gates/market params/field settings) via canaries and replay.
* **Change ledger**: signed diff of params and code with provenance.

### API contracts

* `POST /evo/rollout` `{ "component":"atune", "diff":"...", "replay_uplift":0.12, "canary_plan":{...} }` → `{ "approved":true }`

### SLAs / monitors

* Canary rollback ≤ 2min; require replay uplift > threshold (e.g., +5%) for auto-approve.

### Tests

* Safety net: simulate worst-case drift and verify auto-abort.

---

## 8) Net/LLM Bus (orchestration layer)

### Responsibilities

* **Strict JSON** I/O enforcement for all Atune-invoked arms; schema validation and auto-repair extraction.
* **Budget/timeouts** enforced at the bus level; annotate responses with actual cost for Atune’s ledger.

### API/Config changes

* Add `x-budget-ms` header passthrough; add `x-cost-ms` response header from providers.
* Prompt guards library available to Atune probes.

### Tests

* Contract fuzzer ensures schema recovery > 99% without silent failures.

---

## 9) Observability (shared)

### Responsibilities

* **Unified Atune Ledger sink**: telemetry ingestion from Atune into Neo4j/OLAP store (decisions, gates, FAE terms, probes, market allocations, reflex actions).
* Dashboards: **regret\@compute**, **coverage vs α**, **field hotspots**, **market allocations**, **drift alarms**.

### SLAs / monitors

* Ingestion lag < 5s; dashboard freshness < 30s.

### Tests

* Golden event flow produces a deterministic ledger trace (hash-stable).

---

## 10) Security & Privacy

### Responsibilities

* **PII policy alignment**: Equor rules + Axon redaction + Atune reflex must agree on taxonomy.
* **Secrets isolation**: probes and analyzers run in containers with least privilege; redact in logs.
* **Retention policy**: set TTLs for raw payloads vs. derived signals.

### Tests

* Synthetic PII suite: no leakage across Atune→Unity→Qora pipeline.

---

## 11) Evaluation Harness (joint)

### Responsibilities

* **Deterministic replay** tool that re-runs last N days with fixed seeds and switchable Atune arms (baseline vs. FAE/MAG vs. Pareto).
* **Counterfactual runner**: recompute decisions with alternative allocations; export uplift deltas.

### API

* CLI or `/eval/replay?from=...&to=...&arm=...` → metrics bundle (JSON).

### Tests

* Repro exact numbers across two runs (hash match) with same seeds.

---

# Field Guide: What to build first (in order)

1. **Synapse small-arm probes + embeddings** (tight latency).
2. **Unity protocol endpoint** with budget/deadline handling and `no_action` verdicts.
3. **Equor affect + reflex rules** (JSON endpoints).
4. **Qora reliability service + contradiction hook.**
5. **Observability sink + replay harness** (so we can prove uplift before/after).
6. **Evo canary gate for Atune params/code** (rollout safety).

---

# Acceptance Criteria (Atune+++ can go to canary when…)

* Synapse probe p95 ≤ 80ms; embedding p95 ≤ 40ms; cost header plumbed.
* Unity returns `verdict` + transcript hash; honors budget; `no_action` labeled.
* Equor affect live; reflex rule fetch works; clamps visible in Atune ledger.
* Qora reliability served; contradiction endpoint creates a re-check task.
* Replay harness renders **uplift report** for FAE+MAG vs. baseline.
* Evo canary + rollback tested on a synthetic param change.

---

# Appendix: JSON snippets Atune expects to *receive*

**Affect** (Equor)

```json
{ "curiosity":0.48, "caution":0.61, "integrity":0.72, "fatigue":0.13, "ts":1724200000 }
```

**Mode params** (Synapse)

```json
{ "lambdas": {"epi":0.82, "risk":1.05, "cost":0.58}, "mag_temp":0.95 }
```

**Reliability** (Qora)

```json
{ "source":"rss:nyt", "reliability":0.77, "n":18342, "last_ts":1724190000 }
```

**Unity verdict**

```json
{ "verdict":"approve", "adjudication":{"summary":"...", "confidence":0.74}, "transcript_hash":"sha256:...", "witness":[...] }
```

---

This is the complete “blast radius” for Atune+++. If you want, I can turn this into a ticketed backlog (labels, owners, estimates) mapped to your repo modules and CI gates.
