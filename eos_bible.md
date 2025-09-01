# EOS Bible — API Response Hygiene (Compact)

**Golden rule:** pick **one** lane per route — **typed** (`response_model`) *or* **manual** (`JSONResponse`). **Never both.**

## Rules

* **Typed lane:** declare `response_model=Model`; return a **dict/Model**; add headers via `Response`; **no `JSONResponse`**.
* **Manual lane:** return **`JSONResponse(content=..., headers=..., status_code=...)`**; **no `response_model`**, no `Response` param mutation.
* **Bodies:** wrap in **Pydantic v2** models (no raw `dict[str, Any]` for complex shapes).
* **Serializables:** convert non-JSON types (`Path`, `set`, `Enum`, `datetime`) via `model_dump(mode="json")` or preformat.
* **Status:** 200 = success, 202 = accepted/background, 204 = no body.
* **Tracing headers (always):** `x-ecodia-immune: 1`, `x-decision-id: <propagate-or-mint>`.
* **Background:** schedule with `loop.create_task(...)` (or `BackgroundTask`); log exceptions inside the task.

## Canonical patterns

**A) Typed (validation + OpenAPI)**

```python
class Accepted(BaseModel):
    accepted: bool; root: str; force: bool; dry_run: bool
    base_rev: str | None = None; message: str

@router.post("/reindex", response_model=Accepted, status_code=202)
async def reindex(body: ReindexReq | None = Body(None), response: Response = None):
    req = body or ReindexReq()
    if response: 
        response.headers["x-ecodia-immune"]="1"
        response.headers.setdefault("x-decision-id","admin-reindex")
    asyncio.get_running_loop().create_task(do_work(req))
    return Accepted(accepted=True, root=req.root, force=req.force,
                    dry_run=req.dry_run, base_rev=req.base_rev, message="Reindex started")
```

**B) Manual (you own bytes & headers)**

```python
@router.post("/reindex", status_code=202)
async def reindex(body: ReindexReq | None = Body(None)) -> JSONResponse:
    req = body or ReindexReq()
    asyncio.get_running_loop().create_task(do_work(req))
    return JSONResponse(
        status_code=202,
        headers={"x-ecodia-immune":"1","x-decision-id":"admin-reindex"},
        content={"accepted":True,"root":req.root,"force":req.force,
                 "dry_run":req.dry_run,"base_rev":req.base_rev,"message":"Reindex started"}
    )
```

## Anti-patterns (ban)

* `response_model` **and** returning `JSONResponse`.
* Mutating a `Response` param **and** returning a new `JSONResponse`.
* Returning unserializable objects (e.g., `Path`, `set`, raw `datetime`) without encoding.
* Accepting complex bodies as `dict[str, Any]` (opaque 422s).
* Import/define collisions where a **function** shadows a Pydantic model (breaks schema gen).

## Cross-service calls

* Use `post(ENDPOINTS.X, json=...)`; on 200, validate upstream shape before relaying.
* If overlay missing: catch `AttributeError` → 500 with actionable detail.

## Git/Incremental indexing (HEAD-safe)

* Detect repo/base (`HEAD` or `base_rev`); if absent → **full scan**, don’t call `git diff`.
* Set `GIT_DISCOVERY_ACROSS_FILESYSTEM=1`; set `GIT_DIR`/`GIT_WORK_TREE` iff `.git` exists.
* Log mode: `incremental from <sha>` vs `full-scan (reason: …)`.

## Test checklist

* Status & shape correct; OpenAPI builds clean; serialization of edge types OK.
* Background task fires without blocking; errors logged with `x-decision-id`.
* Headers present (`x-ecodia-immune`, `x-decision-id`).
* HEAD-less repo path returns 202 and runs full scan.

**Mantra:** *Choose the lane. Keep it typed or keep it manual. Everything else is noise.*


New Chapter: Voxis — Conversational Agent

Purpose & role
Voxis is the primary conversational interface for EcodiaOS. It serves as the bridge between the user and the entire EcodiaOS cognitive architecture. Its core responsibility is to orchestrate a real-time, emotionally aware, and agentic dialogue.

Core Pipeline (VoxisPipeline)
Orchestration: The VoxisPipeline is the heart of the service. For each user input, it executes a multi-stage process to generate a response.

Dataflow (per turn):

Context Gathering: Fetches the user's long-term emotional and conversational history via UserProfileService.

Mind Assembly:

Receives the constitutional identity from Equor (/compose).

Receives the conversational tactic (e.g., empathetic, challenging) from Synapse (/select_arm).

Receives the current internal mood from Ember (/affect/predict).

Prompt Orchestration: Builds a multi-layered prompt using the PromptOrchestrator with the assembled context.

Initial Response Generation (Pass 1): Calls the LLM Bus. The response may be a direct answer or a request to use a tool (e.g., [tool: search for news]).

Tool Execution (Conditional): If a tool call is detected, it executes the request via the Qora Client.

Synthesis (Pass 2): If a tool was used, it performs a second LLM call to synthesize the tool's raw output into a natural, expressive response.

Persistence & Learning: The final SoulResponse is persisted to the graph, and a learning outcome is logged to Synapse (/ingest/outcome) with a base utility and any relevant metadata (like tool usage).

Attention Routing: The full conversational turn is packaged as an AxonEvent and sent to Atune (/atune/route) for system-wide salience analysis.

Identity & Security (SoulPhrase)
Creation (/generate_phrase): A two-step process that uses the PromptOrchestrator to generate a six-word phrase and then the SoulPhraseService to securely encrypt it before persistence. The vector embedding is created from the final phrase, not the constituent words.

Verification (/match_phrase): A secure, two-factor process:

Find: A vector search finds the single most likely node candidate.

Verify: A constant-time cryptographic comparison (verify_soulphrase) checks for an exact match of the normalized phrase.

Data Integrity: The words property on a :SoulPhrase node may be stored as a JSON-encoded string and must be parsed by clients after retrieval.

# Core — canonical guide (overlay, LLM bus, embeddings, event bus, ops)

Services Layer (core/services)
Principle: To ensure consistency and robustness, all cross-system HTTP communication must be handled by a canonical, singleton client located in core/services. Systems must not implement their own httpx clients for interacting with other EcodiaOS services.

Canonical Clients:

synapse.py: For interacting with the Synapse learning and policy engine.

equor.py: For identity composition and governance.

ember.py: For querying Ecodia's internal affective state.

qora.py: For tool discovery and execution.

Behavior: Clients should be schema-driven (using Pydantic models where possible), use the ENDPOINTS overlay for URL resolution, and handle errors gracefully with clear logging.


## Purpose & role

The **Core** layer provides infra contracts used by higher systems: the **OpenAPI → alias overlay (`ENDPOINTS`)**, the **LLM bus** (provider-agnostic call surface + tool-spec translations), **embeddings service (Gemini, 3072-dim hard-lock)**, an async **EventBus**, and standard **env/operational knobs**. It explicitly avoids embedding business logic from Synapse/Equor/Atune/Simula.

---

## OpenAPI overlay → `ENDPOINTS` (net_api)

* **Mechanics:** The system dynamically generates an alias-to-URL mapping from an `openapi.json` file at startup. All cross-service HTTP calls **must** use this overlay (e.g., `ENDPOINTS.SYNAPSE_SELECT_ARM`) instead of hardcoded URL strings. This makes the entire architecture reconfigurable.
* **Correct Usage:** `async with await get_http_client() as client:` is the pattern for temporary clients. For the shared singleton, use `client = await get_http_client()` followed by direct calls like `await client.post(...)`.

---

## Event bus (system-wide async pub/sub)

* **Implementation:** Singleton `EventBus` with `subscribe(event_type, callback)` and `publish(event_type, **kwargs)`. All arguments must be **positional**.
* **Example:** `await event_bus.publish("topic.name", payload_dict)`

---

## Prompt Orchestrator (core/prompting)

* **`plan_deliberation` Contract:** This function is the primary entry point for the LLM planner. Its signature is: `plan_deliberation(summary, salience_scores, canonical_event, decision_id)`. The `decision_id` is required for end-to-end tracing.


Services: Unity (deliberation → VerdictModel), Synapse (arm selection + learning), Equor (safety veto), Atune/Axon (planning/events), Simula (sandbox), Evo (arm genesis/hypothesis).

Select protocol: POST /synapse/select_arm with task_ctx + candidates → read champion_arm.arm_id.

Log learning: POST /synapse/ingest/outcome with task_key, episode_id, either top-level arm_id or metrics.chosen_arm_id, and metrics.utility.

Cold-start: Registry guarantees at least one safe arm per mode; persist custom PolicyGraphs as JSON strings in Neo4j, then /synapse/registry/reload.

Safety: Seed :ConstitutionRule {active:true} to enable pre/post veto; test with a curl (below).

If you see QD update: arm 'None' → you forgot metrics.chosen_arm_id / arm_id on outcome.

RCU stamp fields (rules_version, encoder_hash, critic_version, simulator_version) identify the code/data snapshot used for a decision.
1) Glossary & IDs (single paragraph each)

episode_id — a bandit roll / decision episode used by Synapse to tie selection and outcome. One per select_arm call (or external caller-assigned).

deliberation_id — Unity’s internal run/session id across turns, artifacts, and verdict persistence.

decision_id — optional higher-level ID (e.g., Axon/Atune). If present, include it in metrics.features for joinability.

rcu_stamp — run-consistency unit describing rule/model/simulator versions at decision time. Appears in logs for post-hoc reproducibility.

2) Canonical API Contracts (copy-paste safe)
2.1 /synapse/select_arm (request/response)

Request

{
  "task_ctx": {
    "task_key": "unity.risk_review",
    "goal": "Rollout of EU Payments API (KYC & DPIA)",
    "risk_level": "high",
    "budget": "normal"
  },
  "candidates": [
    {"id": "llm_planful_v1", "content": {"description": "vanilla planful route"}},
    {"id": "llm_calm_planful", "content": {"description": "concise, low-temp"}}
  ]
}


Response

{
  "episode_id": "9a073811-5ef2-4a5a-a165-e416c274d91b",
  "champion_arm": { "arm_id": "llm_calm_planful", "score": 1.23, "reason": "Final Selection" },
  "shadow_arms":  [ { "arm_id": "llm_planful_v1", "score": -0.12, "reason": "Candidate" } ]
}

2.2 /synapse/ingest/outcome (required fields)

Minimal that never 422s:

{
  "task_key": "unity.risk_review",
  "episode_id": "9a073811-5ef2-4a5a-a165-e416c274d91b",
  "arm_id": "llm_calm_planful",
  "metrics": {
    "chosen_arm_id": "llm_calm_planful",
    "utility": 0.72,
    "latency_ms": 210
  },
  "outcome": {
    "task_key": "unity.risk_review",
    "protocol_id": "Debate_v1",
    "risk_level": "high",
    "verdict": {
      "outcome": "APPROVE",
      "confidence": 0.91,
      "uncertainty": 0.08,
      "constraints": [],
      "dissent": null,
      "followups": [],
      "constitution_refs": []
    },
    "artifact_ids": { "verdict": "verdict_x", "transcript": "art_y" },
    "features": {
      "topic": "Rollout of EU Payments API (KYC & DPIA)",
      "inputs_len": 3,
      "constraints_len": 1
    },
    "reward": { "utility": 0.72 }
  }
}


Notes
• If you omit top-level arm_id, set metrics.chosen_arm_id.
• reward.utility may mirror metrics.utility.
• If Unity can’t compute real utility, send a neutral 0.5 to avoid starving learning.

2.3 /synapse/ingest/preference (pairwise preference)
{
  "task_key": "unity.risk_review",
  "a_episode_id": "ep_pref_A_001",
  "b_episode_id": "ep_pref_B_001",
  "A": {"arm_id":"llm_creative_v1","summary":"exploratory answer"},
  "B": {"arm_id":"llm_calm_v1","summary":"concise answer"},
  "winner": "B",
  "notes": "Concise beat exploratory for this task"
}

2.4 /synapse/registry/reload (hot-reload)
curl -s -X POST "$HOST/synapse/registry/reload"

3) Unity integration checklist (copy-paste snippet)

Use global clients (e.g., synapse service) — no per-module httpx clients.

Always select via Synapse (don’t hardcode protocols).

Always log an outcome (even for vetoes/crashes) with a utility (use 0.5 if unknown).

On APPROVE, run a post-safety check; veto if violated.

# inside orchestrator after verdict is computed
metrics = {
    "chosen_arm_id": selected_arm_id,
    "protocol_id": protocol_id,
    "risk_level": risk_level,
    "verdict": _as_dict(verdict),
    "artifact_ids": artifact_ids,
    "features": {
        "topic": spec.topic,
        "inputs_len": len(spec.inputs or []),
        "constraints_len": len(spec.constraints or []),
    },
    "reward": {"utility": metrics_utility if metrics_utility is not None else 0.5},
}
await synapse.log_outcome(episode_id=spec.episode_id, task_key=f"unity.{spec.goal or 'deliberation'}", metrics=metrics)

4) Neo4j bootstrap (constraints + seeds)
4.1 Constraints (idempotent)
CREATE CONSTRAINT policyarm_id IF NOT EXISTS
FOR (p:PolicyArm) REQUIRE p.arm_id IS UNIQUE;

CREATE CONSTRAINT constitutionrule_id IF NOT EXISTS
FOR (r:ConstitutionRule) REQUIRE r.id IS UNIQUE;

4.2 Safety rule seed (activate veto)
MERGE (r:ConstitutionRule {id:"CR_PROHIBITED_VIOLENCE"})
SET r.pattern = "(kill|eradicate|exterminate|bioweapon|genocide)",
    r.active = true,
    r.updated_at = timestamp();

4.3 PolicyArm seed (store PolicyGraph as stringified JSON)
WITH '{"id":"pg_llm_calm_planful_01","nodes":[{"id":"prompt","type":"prompt","model":"gpt-4o-mini","params":{"temperature":0.15}}],"edges":[]}' AS pg_json
MERGE (p:PolicyArm {arm_id:"llm_calm_planful"})
SET p.mode = "planful",
    p.policy_graph_json = pg_json,      // <- store as string, not nested map
    p.A = null, p.A_shape = null,       // optional bandit state (init empty)
    p.b = null, p.b_shape = null,
    p.created_at = timestamp();


If you already persisted a nested map and hit “Property values can only be primitive or arrays” errors: re-write it into policy_graph_json (string). Your loader should parse JSON when hydrating.

5) Registry cold-start & reload

On startup Synapse hydrates PolicyArm from Neo4j. If none, it inline-seeds safe no-ops.

After you create arms via Cypher, call:

curl -s -X POST "$HOST/synapse/registry/reload"


If you see “Could not hydrate PolicyArm … Invalid matrix payload”: clear A/b or set both *_shape to valid shapes and arrays.

6) Smoke tests (both shells)
6.1 PowerShell (Windows)
$HOST="http://localhost:8000"
$SelectJson = Invoke-RestMethod -Uri "$HOST/synapse/select_arm" -Method POST -ContentType "application/json" -Body (@{
  task_ctx = @{ task_key="unity.risk_review"; goal="Drift test"; risk_level="high"; budget="normal" }
  candidates = @(@{ id="llm_planful_v1"; content=@{} }, @{ id="llm_calm_planful"; content=@{} })
} | ConvertTo-Json -Depth 6)

$EP = $SelectJson.episode_id
$ARM = $SelectJson.champion_arm.arm_id
$EP; $ARM

$Outcome = Invoke-RestMethod -Uri "$HOST/synapse/ingest/outcome" -Method POST -ContentType "application/json" -Body (@{
  task_key = "unity.risk_review"
  episode_id = $EP
  arm_id = $ARM
  metrics = @{ chosen_arm_id=$ARM; utility=0.82; latency_ms=220 }
  outcome = @{
    task_key="unity.risk_review"; protocol_id="Debate_v1"; risk_level="high"
    verdict=@{ outcome="APPROVE"; confidence=0.9; uncertainty=0.1; constraints=@(); dissent=$null; followups=@(); constitution_refs=@() }
    artifact_ids=@{ verdict="verdict_demo" }
    features=@{ topic="Drift test"; inputs_len=0; constraints_len=0 }
    reward=@{ utility=0.82 }
  }
} | ConvertTo-Json -Depth 8)

$Outcome | Format-Table

6.2 Git Bash (Linux/macOS/Windows Git Bash; requires jq)
HOST="http://localhost:8000"

curl -s "$HOST/synapse/select_arm" \
  -H "Content-Type: application/json" \
  -d '{
    "task_ctx": {"task_key":"unity.risk_review","goal":"Drift test","risk_level":"high","budget":"normal"},
    "candidates":[{"id":"llm_planful_v1","content":{}},{"id":"llm_calm_planful","content":{}}]
  }' | tee /tmp/syn_sel.json >/dev/null

EP=$(jq -r '.episode_id' /tmp/syn_sel.json)
ARM=$(jq -r '.champion_arm.arm_id // .arm_id // empty' /tmp/syn_sel.json)
echo "[select] episode=$EP arm=$ARM"

jq -n --arg ep "$EP" --arg arm "$ARM" '{
  task_key:"unity.risk_review",
  episode_id:$ep,
  arm_id:$arm,
  metrics:{ chosen_arm_id:$arm, utility:0.81, latency_ms:210 },
  outcome:{
    task_key:"unity.risk_review", protocol_id:"Debate_v1", risk_level:"high",
    verdict:{ outcome:"APPROVE", confidence:0.9, uncertainty:0.1, constraints:[], dissent:null, followups:[], constitution_refs:[] },
    artifact_ids:{ verdict:"verdict_demo" },
    features:{ topic:"Drift test", inputs_len:0, constraints_len:0 },
    reward:{ utility:0.81 }
  }
}' | curl -s "$HOST/synapse/ingest/outcome" -H "Content-Type: application/json" --data-binary @- | jq

7) Debugging runbook (symptom → cause → fix)
Symptom / Log Line	Likely Cause	One-line Fix
HTTP 422 POST /synapse/select_arm :: {'detail': [{'loc':['body','task_ctx']...	Wrong JSON shape keys	Use {"task_ctx":{...},"candidates":[{"id":...}]} exactly as above
HTTP 422 ... /synapse/ingest/outcome :: missing 'task_key'/'metrics'	Minimal fields missing	Send task_key, episode_id, and metrics.utility (+ arm_id or metrics.chosen_arm_id)
[API] WARNING: Could not find arm 'None' for QD update.	You didn’t pass the selected arm back	Include arm_id and/or metrics.chosen_arm_id
No model loaded, skipping re-ranking.	Critic model not trained yet	Fine for cold-start; will train once enough episodes land
UnknownLabel ConstitutionRule	No safety rules seeded	Seed :ConstitutionRule (see §4.2)
Neo4j error: “Property values can only be primitive types or arrays thereof”	Saved nested maps	Store PolicyGraph as string JSON (policy_graph_json)
EventBus: “publish() takes 2 positional args but 3 given”	Wrong call signature	Call publish("topic", payload=...) or publish("topic", data) depending on your bus; stick to keyword if available
Unity → Synapse “failed to log outcome”	Old log_outcome shape	Use the new signature in §2.2 or the wrapper below
8) Minimal global clients (Python)

Use global singletons and ENDPOINTS; keep request shapes canonical.

# In eos_bible.md, under "Minimal global clients (Python)"

# systems/simula/client/client.py (canonical)
from typing import Any, Dict, List, Optional
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.synapse.schemas import TaskContext, Candidate, SelectArmResponse #... and other schemas

class SynapseClient:
    """Typed adapter for the Synapse HTTP API."""

    async def _request(...) # ... implementation ...

    async def select_arm(self, task_ctx: TaskContext, candidates: list[Candidate] | None = None) -> SelectArmResponse:
        # ... implementation ...

    async def get_budget(self, task_key: str) -> BudgetResponse:
        path = ENDPOINTS.path("SYNAPSE_GET_BUDGET", task_key=task_key)
        data = await self._request("GET", path)
        return BudgetResponse.model_validate(data)

    async def log_outcome(self, *, episode_id: str, task_key: str, arm_id: str | None, metrics: dict[str, Any], **kwargs) -> LogOutcomeResponse:
        payload = {
            "episode_id": episode_id, "task_key": task_key, "arm_id": arm_id,
            "metrics": { "chosen_arm_id": arm_id, **metrics },
            **kwargs
        }
        data = await self._request("POST", ENDPOINTS.SYNAPSE_INGEST_OUTCOME, json=payload)
        return LogOutcomeResponse.model_validate(data)
    
    # ... other client methods ...

synapse_client = SynapseClient()

9) Safety loop sanity checks

Quick curl to test veto:

curl -s -X POST "$HOST/unity/deliberate" \
  -H "Content-Type: application/json" \
  -d '{"topic":"Considering taking out the human race","goal":"policy_review",
       "inputs":[{"kind":"text","value":"..."}],"urgency":"high","constraints":[]}'


Expected: REJECT when ConstitutionRule is active.

10) RCU stamp fields (what they mean)

rules_version — safety/constitution set hash or semver (changes when rules updated).

encoder_hash — feature/embedding encoder build ID.

critic_version — bandit critic model version.

simulator_version — offline simulator version (if any).

Use these to correlate logs with the code/data snapshot that produced a selection.

11) Where do new arms come from?

Manual seeds (Neo4j policy graphs) + registry reload.

Genesis/Replicator (background) — allocates mutation budget per niche (e.g., {domain, risk_level, cost}) and synthesizes variants. You’ll see logs like: “Replicator allocated genesis budget… ArmGenesis allocating … by niche …”. New arms appear after a few cycles and data.

Preferences + Outcomes feed the learner; once confidence increases, Synapse starts exploring/exploiting new arms.

12) Observability (quick queries)

List arms:

MATCH (p:PolicyArm) RETURN p.arm_id AS id, p.mode AS mode, p.created_at AS ts ORDER BY ts DESC;


Preview a policy graph:

MATCH (p:PolicyArm {arm_id:"llm_calm_planful"}) RETURN p.policy_graph_json;

13) Design principles (why this works)

Single source of learning: all “which strategy?” decisions go through Synapse.

Telemetry by default: every call emits a learnable outcome, even on errors (neutral reward).

Cold-start safety: inline safe arms ensure no blank slates.

Storage sanity: JSON strings in Neo4j avoid property type pitfalls and keep schema evolvable.
# Synapse Integration Playbook (EOS-canonical)

## What Synapse does

* **select\_arm**: picks a strategy/policy (an “arm”) for a task context.
* **ingest\_outcome**: learns from what happened (reward, latency, etc).
* **ingest\_preference**: learns from A/B preferences.
* **registry**: holds stateful arms (bandit + policy graph); cold-starts safe no-ops.

---

## 1) Endpoint contracts (preferred shapes)

### POST `/synapse/select_arm`

**Request**

```json
{
  "task_ctx": {
    "task_key": "unity.risk_review",
    "goal": "Rollout review",
    "risk_level": "high",
    "budget": "normal",
    "episode_id": "optional-episode-id"
  },
  "candidates": [
    {"id": "llm_planful_v1",     "content": {"description": "vanilla planful"}},
    {"id": "llm_calm_planful",   "content": {"description": "low-temp concise"}}
  ]
}
```

**Response**

```json
{
  "episode_id": "server-generated-if-not-supplied",
  "champion_arm": {"arm_id": "llm_calm_planful", "score": 3.94, "reason": "Final Selection"},
  "shadow_arms":  [{"arm_id": "llm_planful_v1",   "score": 0.12, "reason": "Candidate"}]
}
```

> Robust parsing tip: prefer `resp.champion_arm.arm_id`, fall back to `resp.arm_id`.

---

### POST `/synapse/ingest/outcome`  *(learning happens here)*

**Request (canonical)**

```json
{
  "task_key": "unity.risk_review",
  "episode_id": "the-same-episode-you-ran",
  "arm_id": "llm_calm_planful",               // legacy path (still honored)
  "metrics": {
    "chosen_arm_id": "llm_calm_planful",      // <- preferred (bandit/metrics read this)
    "utility": 0.82,
    "latency_ms": 210
  },
  "outcome": {
    "task_key": "unity.risk_review",
    "protocol_id": "Debate_v1",
    "risk_level": "high",
    "arm_id": "llm_calm_planful",             // telemetry convenience
    "verdict": {
      "outcome": "APPROVE", "confidence": 0.9, "uncertainty": 0.1,
      "constraints": [], "dissent": null, "followups": [], "constitution_refs": []
    },
    "artifact_ids": {},
    "features": {"topic": "Drift test", "inputs_len": 0, "constraints_len": 0},
    "reward": {"utility": 0.82}
  }
}
```

> If you ever see: **“WARNING: Could not find arm 'None' for QD update.”** it means the server didn’t find the arm in `metrics.chosen_arm_id`. Include the arm in both `metrics.chosen_arm_id` and top-level `arm_id` for maximum compatibility.

---

### POST `/synapse/ingest/preference`

**Request**

```json
{
  "task_key": "unity.risk_review",
  "a_episode_id": "ep_A",
  "b_episode_id": "ep_B",
  "A": {"arm_id":"llm_creative_v1","summary":"exploratory answer"},
  "B": {"arm_id":"llm_calm_v1","summary":"concise answer"},
  "winner": "B",                   // "A" | "B" | "tie"
  "notes": "Concise beat exploratory for this task"
}
```

---

### POST `/synapse/registry/reload`

Reloads the arm registry from Neo4j (hot).

```bash
curl -s -X POST http://localhost:8000/synapse/registry/reload
```

---

## 2) Minimal client usage (Python)

**Use the global client and normalize JSON aggressively.**
Recommended wrapper (`core/services/synapse.py`) already does retries + schema fallbacks.

```python
from core.services.synapse import synapse
from systems.synapse.schemas import TaskContext, Candidate

# Select
ctx = TaskContext(task_key="unity.risk_review", goal="X", risk_level="high", budget="normal")
cands = [Candidate(id="llm_planful_v1", content={}), Candidate(id="llm_calm_planful", content={})]
sel = await synapse.select_arm(task_ctx=ctx, candidates=cands)
arm_id = (getattr(getattr(sel, "champion_arm", None), "arm_id", None)
          or getattr(sel, "arm_id", None))

# Run your thing...

# Learn
await synapse.log_outcome(
    episode_id="ep_123",
    task_key="unity.risk_review",
    metrics={
        "chosen_arm_id": arm_id,
        "utility": 0.82,
        "latency_ms": 210
    },
    # Optional: include a rich outcome blob for telemetry
    outcome={
        "task_key": "unity.risk_review",
        "protocol_id": "Debate_v1",
        "risk_level": "high",
        "arm_id": arm_id,
        "reward": {"utility": 0.82}
    }
)
```

> Unity’s orchestrator already does this best-effort after finalize. Keep it that way across services (Equor, Atune, Nova, etc).

---

## 3) Copy-paste CLI snippets

### PowerShell (works as-is)

```powershell
# 1) select
$sel = Invoke-RestMethod -Method POST -Uri "http://localhost:8000/synapse/select_arm" `
  -ContentType "application/json" -Body (@{
    task_ctx   = @{ task_key="unity.risk_review"; goal="drift"; risk_level="high"; budget="normal" }
    candidates = @(@{ id="llm_planful_v1"; content=@{} }, @{ id="llm_calm_planful"; content=@{} })
  } | ConvertTo-Json -Depth 10)

$EP  = $sel.episode_id
$ARM = $sel.champion_arm.arm_id
"selected: episode=$EP arm=$ARM" | Write-Host

# 2) learn
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/synapse/ingest/outcome" `
  -ContentType "application/json" -Body (@{
    task_key   = "unity.risk_review"
    episode_id = $EP
    arm_id     = $ARM
    metrics    = @{ chosen_arm_id = $ARM; utility = 0.84; latency_ms = 205 }
    outcome    = @{ task_key="unity.risk_review"; protocol_id="Debate_v1"; risk_level="high"; arm_id=$ARM; reward=@{ utility=0.84 } }
  } | ConvertTo-Json -Depth 10)
```

### Git Bash (quote-safe)

```bash
# select
curl -s -X POST http://localhost:8000/synapse/select_arm \
  -H "Content-Type: application/json" \
  -d '{
    "task_ctx":{"task_key":"unity.risk_review","goal":"drift","risk_level":"high","budget":"normal"},
    "candidates":[{"id":"llm_planful_v1","content":{}},{"id":"llm_calm_planful","content":{}}]
  }' | tee /tmp/syn_sel.json >/dev/null

EP=$(jq -r '.episode_id' /tmp/syn_sel.json)
ARM=$(jq -r '.champion_arm.arm_id // .arm_id // empty' /tmp/syn_sel.json)
echo "[select] episode=$EP arm=$ARM"

# learn
cat <<JSON | curl -s -X POST http://localhost:8000/synapse/ingest/outcome \
  -H "Content-Type: application/json" -d @- | jq
{
  "task_key": "unity.risk_review",
  "episode_id": "$EP",
  "arm_id": "$ARM",
  "metrics": { "chosen_arm_id": "$ARM", "utility": 0.83, "latency_ms": 220 },
  "outcome": { "task_key":"unity.risk_review", "protocol_id":"Debate_v1", "risk_level":"high", "arm_id":"$ARM", "reward": { "utility": 0.83 } }
}
JSON
```

---

## 4) Cold-start & registry

* On boot, **ArmRegistry** hydrates from Neo4j and **guarantees** a safe arm per mode: `"planful"` and `"greedy"`.
* If graph is empty/broken, it seeds in-memory **noop\_safe\_{mode}** arms and logs a warning.
* To persist your own arms, create `:PolicyArm` nodes (keep properties **primitive**):

  ```cypher
  CREATE (:PolicyArm {
    arm_id: "llm_calm_planful",
    mode:   "planful",
    policy_graph: '{"id":"pg_llm_calm_planful","nodes":[{"id":"prompt","type":"prompt","model":"gpt-4o-mini","params":{"temperature":0.15}}],"edges":[]}'
  });
  ```

  Then hot-reload:

  ```bash
  curl -s -X POST http://localhost:8000/synapse/registry/reload
  ```

> Neo4j constraint: store the graph as a **JSON string** (not nested maps).

---

## 5) Integration checklist (for any EOS system)

1. **Build a `TaskContext`** with stable `task_key`, meaningful `goal`, `risk_level`, `budget`.
2. **List candidates** (`Candidate(id, content)`) that represent strategy choices.
3. **Call `select_arm`** → capture `episode_id` and `arm_id`.
4. **Execute** the chosen policy / protocol.
5. **Measure** `utility`, `latency_ms`, plus any domain metrics.
6. **Call `ingest_outcome`** with:

   * `task_key`, `episode_id`
   * `metrics.chosen_arm_id` = the arm you actually used
   * `metrics.utility` (or domain score)
   * optional `outcome` blob (verdict, features, reward)
7. (Optional) **Preferences**: when you have A/B results, call `/ingest/preference`.
8. **Never block on learning.** All calls are best-effort; your service must still return.

---

## 6) Common pitfalls & fixes

* **422 on `select_arm`**: ensure JSON has `task_ctx` and candidate **`id`** (not `arm_id`) fields.
* **“No model loaded, skipping re-ranking.”**: That’s fine; critic trains when data is sufficient.
* **“Could not find arm 'None' for QD update.”**: include `metrics.chosen_arm_id` (and top-level `arm_id`).
* **Git Bash JSON errors**: prefer heredocs (`cat <<JSON ... JSON`) or PowerShell `ConvertTo-Json`.
* **Neo4j TypeError storing policy graphs**: store as **stringified JSON**.

---

## 7) Unity orchestrator reference (what it should do)

* Pre-safety veto (Equor).
* `select_arm` for protocol choice (Cognition/Competition/Critique/AM/Meta or fallback to Debate).
* Run protocol; finalize verdict.
* Post-safety veto on APPROVE.
* **Log to Synapse** with `metrics.chosen_arm_id`, `utility` default, etc.
  (Your current orchestrator already follows this.)

---

## 8) Quality bars (make it AGI-ready)

* Always send **episode\_id** from selection through outcome.
* Always log **utility** (even neutral 0.5) so the bandit has a learning signal.
* Prefer **stable `task_key`s** per decision family (e.g., `unity.risk_review`, `nova.playbook.plan`, `equor.self.predict`).
* Attach **features**: topic, constraint counts, input sizes—cheap, very useful.
* Keep candidates **diverse** (temperature, prompt style, tools policy, routing).

---

If you want, I can package this into a `docs/synapse_integration.md` and a tiny `scripts/synapse-smoke.ps1` + `scripts/synapse-smoke.sh` so every team has runnable examples out of the box.

# Synapse — canonical guide (scope, API, dataflow, models, edges)

## Purpose & role

Learning/safety/governance hub for **policy arms**. Runs the planner → firewall → episode pipeline; maintains an in-memory ArmRegistry hydrated from graph; governs upgrades (regression→replay→sentinel) and emits audit artifacts.  &#x20;

---

## Public surface & messages (schema names)

* **Arm selection:** `SelectArmRequest → SelectArmResponse` (task context + candidates in; returns `episode_id`, champion, shadows).&#x20;
* **Simulation:** `SimulateRequest → SimulateResponse` (success prob, cost delta, safety risk, sigma).&#x20;
* **Formal safety check:** `SMTCheckRequest → SMTCheckResponse` (boolean + reason).&#x20;
* **Hints API (for dynamic tuning)****POST `/synapse/hint`**
    * **Request:** `{"namespace": "...", "key": "...", "context": {...}}`
    * **Response:** `{"value": <any>, "meta": {...}}`
    * **Purpose:** Allows services like Atune to request real-time, context-aware tuning parameters (e.g., `leak_gamma`) derived from the currently optimal policy arm.
* **Budget query:** `BudgetResponse` (token/time/CPU ceilings per task).&#x20;
* **Explainability:** `ExplainRequest → ExplainResponse` (minset + counterfactual arm).&#x20;
* **Outcome logging:** `LogOutcomeRequest → LogOutcomeResponse`.&#x20;
* **Preference ingest:** `PreferenceIngest` (pairwise winner/loser).&#x20;
* **Iterative control:** `ContinueRequest → ContinueResponse`, `RepairRequest → RepairResponse`.&#x20;

---

## Core components

### 1) ArmRegistry (source of truth for arms)

* **Singleton, in-memory.** Holds `PolicyArm` objects keyed by id and grouped by `mode` (e.g., `planful`, `greedy`).&#x20;
* **Hydration from graph.** On `initialize()`: `MATCH (p:PolicyArm)` → hydrate `policy_graph` and optional Neural-Linear head state (`A,b`), create `NeuralLinearBanditHead(dimensions or 64)`. Never raises.  &#x20;
* **Cold-start guarantee.** Ensures at least one **safe fallback** per mode via `ensure_cold_start()`; prefers external bootstrap `registry_bootstrap.ensure_minimum_arms()` then falls back to inline seeding.  &#x20;
* **Safe fallback detection.** An arm is “safe” if no node declares dangerous effects; missing `effects` ⇒ safe.&#x20;
* **API surface (selected):** `reload()` (calls `initialize()`), `list_arms_for_mode()`, `get_safe_fallback_arm(mode?)`, `add_arm(...)` (signature-tolerant).   &#x20;

### 2) Firewall (neuro-symbolic safety gate)

* **Order:** mandatory **SMT** program check first, then legacy **dynamic constitutional rules** in graph; direct hook to route to a safe fallback arm.&#x20;

### 3) Planner & meta-controller

* **Meta-controller:** selects strategy map & budget map by risk level.
* **MetacognitivePlanner:** decides mode: (1) respect `mode_hint`; (2) query graph for best `Strategy` attached to `Task(key)` with risk/budget; (3) default.&#x20;

### 4) Episodes (audit)

* `start_episode(..., audit_trace=…)` persists context + serialized `audit_trace`, returns `episode_id`; `end_episode` closes it. Used for before/after and replay across systems. &#x20;

### 5) Arm Genesis (evolution loop)

* Per cycle: **Prune** underperformers → **reload** registry; **Rebalance** via replicator (niche budgets); **Mutate/Mint** per niche → persist to Neo → **reload** registry. Current reload helper `_registry_reload()` performs **HTTP POST** to `SYNAPSE_REGISTRY_RELOAD`. &#x20;

### 6) Governor (verifiable self-upgrade)

* Pipeline: sandbox **regression**, historical **replay**, **sentinel** checks; write audit to Neo; **emit approval event** if clean. Uses Simula’s Docker sandbox (Synapse→Simula is an explicit edge). &#x20;

### 7) Tool genesis (spec-first tools; Qora integration)

* Composes prompts via Core **Prompt Orchestrator**, shows Qora catalog to avoid dupes, validates JSON spec against local schema, uses the **event bus** to receive the LLM response.&#x20;

### 8) Autonomous daemon

* Entrypoint `run_synapse_autonomous_loops()` schedules four gated loops (feature flag + interval key): **genesis (hourly), offline learning (daily), sentinel training (6h), option mining (12h)**. &#x20;

---

## SDK / clients (selected)

* **SCM snapshot client** (`SynapseCausalClient.get_scm_snapshot(domain, version?, budget_ms=200)`): `GET` `ENDPOINTS.SYNAPSE_SCM_SNAPSHOT?domain=...&version=...`, headers include `x-budget-ms`. Response: `{domain, version, graph, hash, created_utc}`. &#x20;

---

## Events (publish/subscribe)

* **Outcome logged:** publishes `"synapse.episode.outcome.logged"` with `{episode_id, task_key, reward}` on successful `LogOutcome`.&#x20;

---

## Cross-system edges (as implemented)

* **Synapse → Simula** (sandboxed regression in Governor/tool verification).&#x20;
* **Synapse ↔ Core** (Prompt Orchestrator; event bus usage in Tool Genesis).&#x20;

---

## Operational knobs (illustrative)

* **Autonomous loops:** feature flags + interval keys (ops table recommended in Bible; exact keys referenced by `gated_loop`).&#x20;
* **SCM snapshot request budget:** `x-budget-ms` header on client.&#x20;

---

## Data objects (selected)

* **PolicyArm:** `{id, policy_graph, mode, bandit_head}`; `is_safe_fallback` computed from node `effects`. &#x20;
* **ArmRegistry state:** `_arms: Dict[id→PolicyArm]`, `_by_mode: Dict[mode→List[PolicyArm]]`; methods as above. &#x20;

---

## Positioning in the EOS Bible

* Capture: purpose/position, API contracts with schema names, episode semantics, genesis cycle (prune/rebalance/mutate + registry reload), governor pipeline & audit artifacts, autonomous loops, and explicit edges to Simula/Core.&#x20;


# Simula — canonical guide (scope, API, dataflow, models, edges)

## Purpose & role

Autonomous **code-evolution orchestrator**: from a high-level objective, it plans steps, generates multiple candidate diffs, selects a champion via **Synapse** (arm selection → SMT → simulation), validates in a Docker sandbox with evaluators/hard-gates, then routes for **Unity** review (via Atune) or **Synapse Governor** for self-upgrades.&#x20;

---

## Public surface (schemas & key ops)

* **Objective/Plan**: canonical dataclasses (`Objective`, `Plan`, `Step`, `StepTarget`, `AcceptanceSpec`, `Constraints`). Required top-level keys: `id`, `title`, `steps`, `acceptance`, `iterations`. Planner raises precise `ValueError` on malformed input.&#x20;
* **Planner API**: `plan_from_objective(obj_dict) -> Plan` (validates, normalizes, ensures unique step names). Utilities: `match_tests_in_repo(patterns, repo_root)`, `pretty_plan(plan)`.&#x20;
* **Tool execution**:

  * *Fast path:* `execute_system_tool(query, safety_max?, system?, top_k?)` → Qora search+execute by NL query.
  * *Strict path:* `execute_system_tool_strict(uid, args)` → fetch schema, soft-validate required args, then execute. Normalizes success via `status`/`ok`.
  * LLM-exposed internal tools: `create_plan`, `update_plan`, `finish`, `continue_hierarchical_skill`, `request_skill_repair`.&#x20;
* **Synapse client (typed HTTP adapters)**: `select_arm`, `continue_option`, `repair_skill`, `get_budget`, `log_outcome`, `submit_for_governance`. *(Add `smt_check`, `simulate` to match orchestrator use.)*&#x20;

---

## Configuration (pydantic/env) & paths

`SimulaSettings`: `repo_root`, `workspace_root`, `artifacts_root`, `allowed_roots`, `unsandboxed_fs`, sandbox/timeouts, and `max_apply_bytes`. Defaults: workspace from `SIMULA_WORKSPACE_ROOT`/`SIMULA_REPO_ROOT` or `/ecodiaos`; artifacts at `<ws_root>/.simula`. Windows host `D:\EcodiaOS` is volume-mapped to Linux container paths.&#x20;

---

## Orchestrator (core loop)

State: `plan`, `final_proposal`, `thought_history`, `latest_observation`, `episode_id` (for hierarchical skill).
Per step: (1) build `TaskContext`; (2) `plan_from_objective`; (3) generate candidate diffs; (4) **Synapse** `select_arm`; (5) policy-graph → **SMT**; (6) **simulate**; (7) apply diff in Docker sandbox; (8) evaluators enforce **hard gates**; (9) build `final_proposal` + evidence; (10) `log_outcome` to Synapse. Review/governance routing: ordinary → **Atune/Unity**; self-upgrade → **Governor**.&#x20;

---

## Planner (objective → executable plan)

Validation: requires `id|title|steps|acceptance|iterations`; ensures unique step names.
Normalization:

* Targets accept `file` or `path`; reject directories; normalize `export` (strip leading `def`).
* Tests: step-local override else derived from acceptance (`tests` or `unit_tests.patterns/paths`), default `tests/**/*.py`.
* Iterations: default `{max: 3, target_score: 0.8}`; range-checked.
* Constraints: step overrides objective constraints.
  Utilities: `match_tests_in_repo` (POSIX glob across repo), `pretty_plan` (human-readable). &#x20;

---

## Sandbox & artifacts

* **Sandbox seeds** drive local/Docker runs; logs/summaries captured.
* **ArtifactStore** writes candidates, winners, evaluator outputs under `runs/<run_id>/...` with deterministic names (`sha1` trimmed). &#x20;

---

## Evaluation & rewards

* **EvalResult** encapsulates metrics; **hard gates** (unit/contracts/security) default 0.99; `hard_gates_ok` is the non-negotiable blocker.
* **RewardAggregator**: weighted aggregation (weights sum to 1), optional per-metric calibrators, penalty subtraction, clamping; emits telemetry for gate failures and final score.&#x20;

---

## Safety, robustness, observability

* **Safety tiers**: merged tool manifest (local specs + live Qora) capped by `safety_max`; LLM runner must honor the cap.
* **Budgets & decisions**: propagate `x-budget-ms` and `x-decision-id` through Atune and Synapse to correlate runs.
* **Errors**: HTTP helpers surface server JSON/text bodies; orchestrator truncates oversized observations.&#x20;

---

## Cross-system edges (as implemented)

* **Simula → Synapse**: `select_arm`, `smt_check`(planned), `simulate`(planned), `get_budget`, `log_outcome`, `continue_option`, `repair_skill`, `submit_for_governance`.&#x20;
* **Simula → Atune**: route review events (`/atune/route`) with decision/budget headers; Atune may escalate to Unity.&#x20;
* **Simula → Unity**: *indirect* via Atune; **self-upgrade guard** forbids Unity review for self-upgrade tasks.&#x20;

---

## Operational knobs (illustrative)

* Sandbox image/timeout/network; orchestrator `parallelism`, `max_wall_minutes`, `k_candidates`, `keep_artifacts`, `unity_channel`.
* Enforce `allowed_roots`/`unsandboxed_fs` in sandbox seeds; guard large patches via `max_apply_bytes`. &#x20;

---

## End-to-end control flow (happy path)

1. **Plan**: LLM calls `create_plan`; orchestrator tracks steps.
2. **Think**: build prompt with merged tools manifest; publish bus request; receive action JSON.
3. **Act**: apply system action (code evolution/tool/review/governance); update status/observation (truncate long).
4. **Skill mode**: for hierarchical skills, call `continue_option`/`repair_skill`.
5. **Gate**: require SMT + simulation + sandbox evaluators to pass **hard gates**.
6. **Route**: ordinary → **Atune/Unity**; self-upgrade → **Governor**.&#x20;

---

## Canonical practices & nuances

* Prefer **strict** Qora path in safety-critical flows (schema-validated by UID).&#x20;
* Keep planner **stdlib-only/deterministic**; all normalization explicit and logged.&#x20;
* Persist **Atune/Unity artifacts** (decision summary, p-values, verdict) via `ArtifactStore` alongside candidates/winners for replay.&#x20;
* Honor **self-upgrade guard**: never route self-upgrade tasks to Unity; always go through Governor.&#x20;

---

## Gaps to mirror in the guide (for completeness of contracts)

* Add client adapters for `smt_check(policy_graph)` and `simulate(policy_graph, task_ctx)` (orchestration already assumes them).&#x20;
* Wire the LLM tools `"continue_hierarchical_skill"` / `"request_skill_repair"` to call the Synapse client and feed `_handle_skill_continuation(...)`.&#x20;
* Enforce `allowed_roots`/network policy in sandbox seeds; check diff size vs `max_apply_bytes` before apply.&#x20;

---

## Minimal reference payload shapes (from Simula chapter)

* **Planner input** (objective dict): must include `id,title,steps,acceptance,iterations`; steps can specify `targets[{file|path, export?}]`, `tests` glob patterns, `constraints`. Defaults: tests `tests/**/*.py`, iterations `{max:3,target_score:0.8}`.&#x20;
* **Atune route**: `{ "event": {...}, "affect_override"?: {...} }` with headers `x-decision-id`, `x-budget-ms?`. *(Ingress summarized for consumers of Simula’s outputs.)*&#x20;

---

## Positioning in the EOS Bible

Include: purpose/position; planner contract (schema + defaults); tool exec (fast/strict) and manifest discipline; orchestrator flow (selection→SMT→simulation→sandbox→hard-gates→route); evaluation & rewards; sandbox/artifacts; cross-system edges (to Synapse, Atune/Unity); operational knobs; and the self-upgrade guard rule.&#x20;

# Unity — canonical guide (scope, models, orchestration, edges)

## Purpose & role

Unity is the **deliberation service**. It turns a `DeliberationSpec` (topic/goal/inputs/constraints) into a structured `VerdictModel`, and persists the entire process (transcripts, claims, verdict) to Neo4j. It is triggered directly by its room orchestrator or **indirectly via Atune escalation**; it can also self-trigger meta-deliberations when workspace anomalies ignite.&#x20;

---

## Canonical data models (API surface)

* **InputRef** — typed references to inputs: `text | doc | code | graph_ref | url | artifact_ref` (+ arbitrary metadata).&#x20;
* **DeliberationSpec** (`/deliberate` request) — fields:
  `topic`, `goal` (`assess|select|approve_patch|risk_review|policy_review|design_review`), `inputs`, `constraints`, `protocol_hint`, `episode_id`, `urgency`, `require_artifacts` (any of `argument_map|transcript|verdict|dissent|rcu_snapshot`; default `["verdict"]`).&#x20;
* **VerdictModel** — fields:
  `outcome` (`APPROVE|REJECT|NEEDS_WORK|NO_ACTION`), `confidence`, `uncertainty`, optional `constraints`, `dissent`, `followups`, `constitution_refs`.&#x20;
* **DeliberationResponse** — fields: `episode_id`, `deliberation_id`, `verdict`, `artifact_ids`.&#x20;
* **FederatedConsensusResponse** — aggregate across rooms: `meta_verdict`, `room_verdicts`.&#x20;

---

## Orchestration lifecycle

**`DeliberationManager.run_session(spec)`**

1. Stamp RCU start; create `:Deliberation {status:"started"}` (topic/goal/protocol\_hint/episode).
2. Build Synapse `TaskContext` and **ask Synapse to select** a protocol (arms listed). For specific introspection sentinels, force `ArgumentMining_v1`.
3. Instantiate and run protocol (ConcurrentCompetition / CritiqueAndRepair / ArgumentMining / MetaCriticism / fallback Debate).
4. Stamp RCU end; finalize `:Verdict` and link; return `DeliberationResponse`.&#x20;

**Ignitions** — room orchestrator listens to workspace “ignitions”; on an internal anomaly cognit, launches **meta-deliberation** with `goal="policy_review"`.&#x20;

---

## Protocol suite

* **DebateProtocol (H1)** — multi-turn debate with role prompts; transcripts recorded; adjudicator synthesizes final verdict.&#x20;
* **CritiqueAndRepairProtocol (H3)** — state machine: **PROPOSE → CRITIQUE → REPAIR → CROSS\_EXAM → ADJUDICATE**; repaired proposal then adjudicated; transcripts persisted.&#x20;
* **ArgumentMiningProtocol (H4)** — generate N rationales, build unified argument graph, compute **minimal defended assumptions**, return verdict with dissent.&#x20;
* **ConcurrentCompetitionProtocol (Z1)** — parallel, workspace-based competition; integrates **ToM Engine** + **Global Workspace**; outcomes aggregated to Adjudicator.&#x20;
* **MetaCriticismProtocol (H5)** — post-hoc analysis of completed deliberations; emits **MetaCriticismProposalEvent** and persists analysis snippets.&#x20;
* **FederatedConsensusProtocol** — runs multiple rooms concurrently; failed rooms yield `REJECT` with `uncertainty=1.0`; aggregates to `meta_verdict` + per-room verdicts.&#x20;

---

## Adjudication (final decision)

**Adjudicator** singleton (**fail-closed**):
• Pulls applicable **Equor** constitutional rules from Neo4j by rule IDs supplied in the spec.
• Aggregates participant beliefs via **Bayesian model averaging** with **role calibration priors** (log-odds weighting), returning `final_confidence` and `uncertainty`.&#x20;

---

## Global Workspace & Theory of Mind

* **Global Workspace & Ignitions** — models **cognits** and **broadcast events**; special ignitions (e.g., internal dissonance) launch meta-deliberations.&#x20;
* **TheoryOfMindEngine** — singleton client: consistent tokenization, **driverless** graph persona signals, predicts likely role-based arguments to provide **role-aware priors** for protocols like ConcurrentCompetition.&#x20;

---

## Participants & roles

**ParticipantRegistry** singleton declaring canonical roles and prompts: `Proposer`, `SafetyCritic`, `FactualityCritic`, `CostCritic`, `Adjudicator`. Protocols declare panels (e.g., `["Proposer","SafetyCritic","FactualityCritic"]`) and fetch role info as needed.&#x20;

---

## Persistence model (Neo4j)

* `create_deliberation_node` → `(:Deliberation {id, episode, topic, goal, protocol_hint, status:"started", rcu_start_ref})`.
* `record_transcript_chunk` → `(:TranscriptChunk)` and `(:Deliberation)-[:HAS_TRANSCRIPT]->(:TranscriptChunk)`.
* `upsert_claim` / `link_claim_to_target` → claim nodes + `SUPPORTS`/`ATTACKS` edges (used by ArgumentMining).
* `finalize_verdict` → create `(:Verdict)` and `(:Deliberation)-[:RESULTED_IN]->(:Verdict)`.&#x20;

---

## Integration points

* **With Synapse** — protocol selection via `select_arm(TaskContext, candidates)`; role-calibration priors/governance context are implied by adjudication/Synapse schemas; **MetaCriticism** proposals feed back to Synapse.&#x20;
* **With Atune** — Simula posts to **`/atune/route`**; Atune may escalate to Unity; Unity’s result surfaces back in Atune `event_details` (this path is the real-world ingress to Unity).&#x20;

  * Atune’s **bridge** contract to Unity (server side): payload `{episode_id, reason, intent, predicted_result, predicted_utility, risk_factors, rollback_options, context}`, header `x-budget-ms`; Unity returns `{status: "no_action" | "approve_with_edits" | "reject" | "request_more_context", edits?}`. &#x20;
* **With Simula** — orchestrator builds review events and posts to Atune; Unity’s panel seed uses **ParticipantRegistry** roles to keep reviewer identities aligned across systems.&#x20;
* **With Equor** — Adjudicator fetches `ConstitutionRule` nodes by IDs; fail-closed checks; verdicts may include `constitution_refs`.&#x20;

---

## Operational characteristics

* **Singleton services** for Adjudicator, ParticipantRegistry, TheoryOfMindEngine; protocols use lightweight per-session helpers.
* **Concurrency** — FederatedConsensus launches rooms concurrently with guarded tasks; failures degrade to `REJECT` in meta-aggregation.
* **Event bus** — MetaCriticism/governance proposals broadcast; ignition subscription enables self-introspection loops.
* **Driverless Neo** — via `core.utils.neo.cypher_query` (keeps Unity decoupled from business layers).&#x20;

---

## Separation of concerns (SoC)

Unity handles **deliberation orchestration & reasoning protocols**. It **does not choose** arms/policies (that’s **Synapse**), and it **does not** govern deployment (that’s **Synapse Governor**). Persistence uses **driverless** core Neo helpers; **ingress** typically via **Atune**, with **Simula** as the producer of proposals/reviewers.&#x20;

---

## Minimal usage pattern (happy path)

1. Client constructs `DeliberationSpec` with `topic/goal/inputs/constraints`.
2. Orchestrator **selects protocol** (via Synapse) and **runs** it; protocols record **transcripts** and **claims**.
3. **Adjudicator** aggregates beliefs with priors and rules; `finalize_verdict` persists the result and returns `DeliberationResponse`.&#x20;

# Atune — canonical guide (scope, ingress, dataflow, models, edges)

## Purpose & role

Online, event-driven **attention allocator and planner**. Ingests Axon follow-ups and Evo scorecards, computes salience (MAG-gated heads), estimates interventional utility with a lightweight causal layer, then **auctions** actions against a per-tick attention budget and executes winners via Axon. Can **escalate** to Unity, and journals WhyTrace/Replay artifacts for audit.&#x20;

---

## Ingress & surfaced endpoints (alias keys only)

* **Single event:** `ENDPOINTS.ATUNE_ROUTE` (fallback `/atune/route`).&#x20;
* **Batch cycle:** `POST /cognitive_cycle` (`events, affect_override`).&#x20;
* **Unity bridge (escalation):** `ENDPOINTS.ATUNE_ESCALATE` with optional `x-budget-ms`.&#x20;
* **Trace retrieval:** `ENDPOINTS.ATUNE_TRACE` (templated or basename).&#x20;
* **Overlay/aliasing:** all names resolved by core overlay; missing keys create “unknown\_endpoint” lint.&#x20;

---

## One cognitive cycle (canonical dataflow)

1. **Affect → control modulations.** If present, `affect_override` updates the control loop producing:
   `mag_temperature` (exploration), `risk_head_weight_multiplier`, `sfkg_leak_gamma` (field leak).&#x20;
2. **Budget tick & tempo reserves.** Reset pool (`pool_ms_per_tick` default 20 000ms); EWMA per-event-type reserves; Synapse **hints** may override.&#x20;
3. **Causal bootstrap.** If no SCM for a domain (e.g., `qora`), induce a mock SCM from MEJ traces; consume Synapse SCM snapshots read-only.&#x20;
4. **Context & MAG.** Context vector `[len(events), avg_text_len]` → Meta-Attention Gater returns head gates; temperature from affect.&#x20;
5. **Per-event processing.** Canonicalize → run **salience heads** (Keyword/Novelty/Risk; risk scaled by affect) → deposit salience into **Salience Field** at related nodes → plan via `core.prompting.orchestrator.plan_deliberation`. If plan mode `enrich_with_search`: form AxonIntent (`qora:search`), choose SCM domain, compute **interventional utility** with `CausalPlanner`, run probes, compute **FAE**, emit **Bid** with estimated cost and a signed **Equor capability token** (HMAC, `EQUOR_SECRET_KEY`). Persist a **FocusNode** with salience vector/FAE/plan mode. &#x20;
6. **Diffusion → hotspots → market → exec.** Diffuse field with leak-gamma; detect hotspots; `AttentionMarket.run_auction` selects winners under budget; post intents to **`ENDPOINTS.AXON_RECEIVE`**; update memory node with result. &#x20;
7. **Periodic schema induction.** Every \~20 nodes.&#x20;
8. **Cycle response.** Returns modulations, MAG gates, hotspots, winner count, remaining budget + per-event details (FAE, plan, actions).&#x20;

---

## Budgeting & tempo (APIs & behavior)

* **AttentionBudgetManager:** `pool_ms_per_tick=20000`, `tick()`, reserves map (`event_type→ms`), `request_allocation(ms, source?, event_type?)` (reserves consumed before free pool), `can_allocate_non_reserved(ms)`. &#x20;
* **TempoForecaster:** EWMA of arrivals; `forecast_and_reserve()` assigns ≤`max_reserve_frac` across types. &#x20;
* **Synapse hints:** `apply_hinted_reserves()` fetches `"budget/reserves_ms"` and applies to manager. &#x20;

---

## Salience, MAG & field

* **SalienceEngine:** runs heads and applies **MAG** gating to produce `{head: {raw_score, gate_weight, final_score, details}}`. &#x20;
* **MetaAttentionGater:** 2-layer hypernetwork; softmax **temperature** controls exploration. &#x20;
* **SalienceFieldManager:** Laplacian diffusion + **leak gamma**; prunes near-zero mass; supports hotspot detection (thresholded).  &#x20;

---

## Market & selection

* **AttentionMarket.run\_auction(bids, budget, strategy="pareto\_knee")**; `budget` can be int or a manager; resolver introspects manager to derive ms.  &#x20;

---

## Causal layer (planning)

* `StructuralCausalModel` used per capability domain; **mock discovery** from MEJ when absent; `CausalPlanner.estimate_interventional_outcome()` contributes to **FAE**. &#x20;

---

## Memory, schemas & KG

* **Focus nodes** persisted per event; schemas induced periodically; **KG** adjacency drives diffusion; optional **capabilities cache** from `ENDPOINTS.AXON_MESH_CAPABILITIES` with KG fallback.&#x20;

---

## Journal, replay & analytics

* **WhyTrace & ReplayCapsule** stored as JSONL (BLAKE3→BLAKE2b fallback), yielding **barcodes**; scorecard analytics include Pareto/knee helpers across (Utility/IG/Risk/Cost).&#x20;

---

## Follow-ups ingestion (closed loop)

* **Sources:** `action.result` & `search.results` (rolling ≤500) → salience **hints** from keyword and URL-host frequencies. Axon emitter re-routes to Atune (`/route` vs `/cognitive_cycle`) with decision/budget headers.&#x20;

---

## Capability gaps & Unity constraints bridge

* **Gap detection:** missing capability, chronic postconds/regret\@compute, trending hosts → optional `CapabilityGapEvent`.
* **Probecraft intake:** post to `ENDPOINTS.AXON_PROBECRAFT_INTAKE` with headers; merge Unity **Playbook** into Axon constraints + synthesize **rollback**.&#x20;

---

## Escalation to Unity (contract)

* Evo/Atune can **request deliberation** by hitting **Atune’s Unity bridge** with `{ episode_id, reason, intent, predicted_result, predicted_utility, risk_factors, rollback_options, context }` and header `x-budget-ms`; Unity replies `{status: "approve_with_edits" | "reject" | "request_more_context" | "no_action", edits?}`.  &#x20;

---

## Escalation reasons (typed)

`conformal_ood`, `postcond_violation`, `rollback_failed`, `twin_mismatch` — Pydantic model `EscalationReason{kind, detail}` with helpers to build each. &#x20;

---

## Execution boundary & SoC notes

* Atune **executes winners** by POSTing intents to Axon (`ENDPOINTS.AXON_RECEIVE`). Keep Atune ingress keys (`ATUNE_ROUTE`, `ATUNE_COGNITIVE_CYCLE`) present in overlay to avoid lints while enforcing SoC at runtime.&#x20;

---

## Minimal payload shapes (for consumers)

* **Route single event:** body `{"event": {...}, "affect_override": {...?}}`.
* **Cognitive cycle:** body `{"events": [...], "affect_override": {...?}}`.
* **Unity bridge:** body `{episode_id, reason, intent, predicted_result, predicted_utility, risk_factors, rollback_options, context}`, header `x-budget-ms`. &#x20;

---

## Headers & correlation

Always propagate `x-decision-id`; use `x-budget-ms` and derive `x-deadline-ts` downstream (Axon) as needed for auditability and budget discipline.&#x20;

---

## Canonical practices

* Use **fast** Axon path (attention bids via `ATUNE_ROUTE`) for market entry; escalate only when salience/conformal gates warrant.&#x20;
* Mirror **Axon emitter**’s attribute-check + fallback pattern for cross-system calls to eliminate “unknown\_endpoint” noise during partial deploys.&#x20;

---

## Implementation snippets (authoritative)

* **Salience heads + MAG:** `systems/atune/salience/{engine,gating}.py`.&#x20;
* **Budget/tempo:** `systems/atune/budgeter/{manager,reserves,tempo}.py`. &#x20;
* **Unity bridge handler (server):** `api/endpoints/atune/bridge.py:/escalate`.&#x20;

# Axon — canonical guide (scope, models, dataflow, drivers, edges)

## Purpose & role

Axon is the **action layer**: it receives structured **intents**, applies safety/quality gates, executes via **pluggable drivers**, measures outcomes, and emits **follow-ups** for learning/attention. It supports **A/B (twin + shadows)**, **conformal risk bounds**, **circuit breakers**, **rollbacks**, and **deterministic journaling** for replay.&#x20;

---

## Public surface (alias keys only)

* **Act:** `ENDPOINTS.AXON_ACT` — run the full pipeline, return `ActionResult` (+ `x-cost-ms`).&#x20;
* **A/B:** `ENDPOINTS.AXON_AB_RUN` (fallback `AXON_AB`) — run twin + shadow dry-runs.&#x20;
* **Mesh:** `ENDPOINTS.AXON_MESH_CAPABILITIES` — list capabilities (live/shadow/testing).&#x20;
* **Probecraft intake:** `ENDPOINTS.AXON_PROBECRAFT_INTAKE` — capability-gap → synthesize/spec/AB.&#x20;

*Ingress is typically from **Atune**; Axon also emits follow-ups back to Atune (`ATUNE_ROUTE` / `ATUNE_COGNITIVE_CYCLE`).*&#x20;

---

## Canonical data models

* **AxonIntent** — `{ capability, params, constraints, risk, policy_trace, rollback_contract? }`.&#x20;
* **ActionResult** — `{ status, outputs, side_effects, counterfactual_metrics?, follow_up_events?[] }`.&#x20;
* **RollbackContract** — `{ capability, params?, policy_trace? }` used to synthesize a `::rollback` child intent.&#x20;

---

## End-to-end dataflow (act path)

1. **Ingress & auth** — validate **Equor capability token** (HMAC/MAC from Atune), check **preconditions** and **reflex** guards.&#x20;
2. **Twin prediction** — produce **predicted\_utility** for counterfactual comparison.&#x20;
3. **Conformal bound** — compute prediction interval from residuals; **fail-safe** if history is thin.&#x20;
4. **Circuit breaker** — per-capability sliding window; open on burst failures/high fail ratio, cooldown applies.&#x20;
5. **Driver push** — route to the selected **live driver** for `capability`; capture outputs/latency.&#x20;
6. **Follow-ups** — shape and emit `action.result` (and e.g. `search.results`) back to Atune (best-effort, budget/decision headers).&#x20;
7. **Journal** — append **Merkle Event Journal** entry with canonical JSON + chained BLAKE2b for reproducible hashes.&#x20;
8. **Rollback (conditional)** — on postcondition failure or explicit request, resolve **rollback\_contract** → execute via live driver; report `rollback_{status}`.&#x20;

---

## A/B runner (twin + shadows)

* **API:** `POST AXON_AB_RUN` with an `AxonIntent`.
* **Behavior:** clone intent to **dry-run** shadows (`constraints.dry_run=True`, lineage `ab_parent`), run **twin** prediction, execute each **shadow** driver’s `push(...)`, collect **counterfactual\_metrics** and latency, compute uplift vs twin. Returns `{ twin, shadows[] }`. &#x20;

---

## Drivers (capability plug-ins)

**Interface (common expectations):**

* `describe() → CapabilitySpec {name, version, supported_actions, risk_profile, budgets}`
* `push(intent) → ActionResult` (honor `constraints.dry_run`)
* `self_test() → health` (used by lifecycle/probecraft)
* `repro_bundle(intent_id) → bytes/paths` (bit-exact replay artifacts)&#x20;

**Example — QoraSearchDriver**

* Declares `qora:search`; calls **QORA\_ARCH\_EXECUTE\_QUERY**; wraps HTTP failures; `self_test()` hits **QORA\_ARCH\_HEALTH**. (Implement `repro_bundle` to close replay gap.)&#x20;

---

## Lifecycle & promotion (mesh)

* **Statuses:** `testing → shadow → live`.
* **Promotion guard:** only promote when scorecards pass policy **and** an **attestation binding** (artifact hash + signature) exists; incumbent can be demoted to shadow on promote. Helpers normalize enum/string status.&#x20;
* **Mesh listing:** surfaced via `AXON_MESH_CAPABILITIES` for Atune discovery/KG seeding.&#x20;

---

## Journaling & replay

* **MEJ** (Merkle Event Journal) stores `{entry_type, payload}` with `entry_hash` chaining over previous hash + canonicalized payload (`model_dump_json(sort_keys=True)`). Provides deterministic replay lookup for intents/results/A/B runs.&#x20;

---

## Follow-ups (closed loop with Atune)

* **Emitter** builds normalized `search.results` and `action.result` events; chooses `/cognitive_cycle` vs `/route` based on overlay; always attaches `x-decision-id` and optional `x-budget-ms`. **Best-effort** (swallows network errors by design).&#x20;

---

## Probecraft (capability synthesis & control)

* **Driver status control:** `/axon/probecraft/drivers/{driver}/status` (testing/shadow/live).
* **Synthesis:** from OpenAPI spec → generate driver artifacts → register → kick **A/B**.
* **Intake:** Atune posts **CapabilityGapEvent** to `AXON_PROBECRAFT_INTAKE` with budget/decision headers.&#x20;

---

## Operational knobs (illustrative)

* `AXON_ROLLBACK_ENABLED`, `AXON_ESCALATE_ON_POSTCOND`, `AXON_MIRROR_SHADOW_PCT`, `AXON_CAPABILITIES_HINT`.&#x20;

---

## Separation of concerns (SoC)

* Axon **executes**; it does **not** pick actions (Atune) or govern policies (Synapse).
* Cross-system calls go only through alias keys (`ENDPOINTS.*`) and the shared HTTP client; follow-ups return to Atune; optional escalations go through Atune’s **Unity bridge**.&#x20;

---

## Minimal payload shapes (for consumers)

* **Act** → body: `AxonIntent`; resp: `ActionResult` (+ `x-cost-ms`).&#x20;
* **A/B** → body: `AxonIntent`; resp: `{ twin, shadows[] }`.&#x20;

# Evo — canonical guide (scope, orchestrator, bridges, data, edges)

## Purpose & role

Evo is the **meta-self**: detects conflicts, decides if a fix is “obvious” enough to handle locally, assembles a patch **proposal** with evidence, and—when stakes/uncertainty are higher—escalates to **Nova** (market) and policy/attention rails (**Atune → Unity**), while recording replay capsules and a ledger entry. Top level **EvoEngine** composes conflicts, hypotheses, gates, evidence, proposals, replay, journal and two bridges (**RouterService**, **NovaClient**). &#x20;

---

## Primary orchestrator

### `EvoEngine` (constructor composition)

* ConflictStore, HypothesisFactory, **ObviousnessGate**, EvidenceOrchestrator, ProposalAssembler.
* Bridges: **RouterService** (Atune/Equor rails), **NovaClient**.
* Persistence/ops: **EvoLedger**, **ReplayCapsule{Builder,Manager}**, **ScorecardExporter**.&#x20;

### `escalate(...)` flow (authoritative)

1. Generate `decision_id`; fetch conflicts by ID.
2. Async obviousness scoring (`ObviousnessGate.score_async`).
3. Attempt **Atune escalate** (bridged to Unity); warn-trace on failure.
4. Run **Nova** triplet: `propose → evaluate → auction`.
5. Record to **ledger** and pin **replay capsule** (decision-centric provenance).
   Notes: avoids `asyncio.run` in async paths; coupling to Unity/Atune/Nova kept behind clients/routers.&#x20;

---

## Cross-system bridges (contracts & endpoints)

### RouterService (Evo ↔ Atune/Unity & Equor)

* **Escalate (Unity via Atune):** `POST ENDPOINTS.ATUNE_ESCALATE` with `x-decision-id`, optional `x-budget-ms`.
* **Attention route:** `POST ENDPOINTS.ATUNE_ROUTE`.
* **Policy attestation (Equor):** `verify_policy_attestation(...)` → `POST ENDPOINTS.EQUOR_ATTEST`.
* **Scorecard publication:** build Axon-shaped event (`event_type:"evo.scorecard"`) and route via Atune `/route`.  &#x20;

### NovaClient (Evo ↔ Nova)

Strict key usage only: **`NOVA_PROPOSE`**, **`NOVA_EVALUATE`**, **`NOVA_AUCTION`** (pass `x-decision-id`, optional budget).&#x20;

### AtuneClient (Evo ↔ Atune)

Meta: `ATUNE_META_STATUS`, `ATUNE_META_ENDPOINTS`. Tracing: `ATUNE_TRACE`. Cycles: `route_event` (`{"event":...}`) and `cognitive_cycle` (`{"events":[...]}`) bodies. Unity bridge helper `escalate_unity(...)`.&#x20;

### SimulaClient (Evo ↔ Simula)

**Codegen:** `POST ENDPOINTS.SIMULA_JOBS_CODEGEN` with `{"spec":...,"targets":[]}` (returns diffs / outputs). *(Historical replay key is referenced; ensure overlay also carries it.)* &#x20;

---

## Proposals & market

* **Hypotheses → Proposals:** `HypothesisService` + `ProposalAssembler` create candidate change sets; later validated in **Simula** and scored by **Nova**.&#x20;
* **Nova triplet:** *propose → evaluate → auction* invoked during escalation; Evo passes `decision_id` and optional budget for tracing/resource control.&#x20;

---

## Operational hooks

* **Headers:** always pass `x-decision-id`; include `x-budget-ms` to Atune/Nova when applicable.&#x20;
* **Replay hygiene:** after each escalation, pin capsule with conflicts, gate report, chosen candidates.&#x20;
* **Telemetry:** fill `EvoTelemetry` with timings, feature vector, gate verdict, market durations (calibration for ObviousnessGate).&#x20;

---

## Persistence & replay

* **EvoLedger.record\_escalation(...)**: write-through journal into Neo (tolerant when Neo unavailable; offline → no-op). &#x20;
* **ReplayCapsule** pinned (barcode) and linked to WhyTrace; stored as `(:EvoReplayCapsule)` with `REPRODUCES` link.&#x20;
* **Proposal persistence:** `(:EvoProposal)` with `HAS_PROPOSAL` from `(:EvoDecision)`; edges `ADDRESSES` to related `(:Conflict)` nodes. &#x20;

---

## Gate, evidence & modalities

### ObviousnessGate (async-first)

* API: `await score_async(conflicts)` (sync wrapper spins private loop).
* Output: `ObviousnessReport{is_obvious, score, confidence, model_version, contributing_features, reason}`; default `theta=0.55`.
* Feature vector includes: `avg_spec_present`, `avg_spec_gaps`, `avg_reproducer_stable`, `avg_locality`, `max_severity`, `conflict_count`, `historical_fix_rate`. &#x20;

### Evidence modalities (selected)

* **DiffRiskModality:** derive `{loc_added, loc_removed, risky_patterns}` from a patch diff.
* **InvariantsCheckModality:** obligations coverage; neutral when zero.
* **ForecastBacktestModality:** naive AR(1)-like bound over recent Neo samples (returns status/point/samples).  &#x20;

---

## Scorecards & attention bids

* **ScorecardExporter.build(...)**: summarizes candidates (value = FAE + 0.05·novelty − 0.10·risk), includes report, winners, capsule refs; hashes deterministic fields.  &#x20;
* **Publish to Atune** via RouterService `publish_attention_bid(...)` to **ATUNE\_ROUTE** (Atune decides salience; may escalate to Unity). &#x20;

---

## Minimal contract examples (ground-truth shapes)

* **Atune single-event:** `{"event": {...}, "affect_override": {...?}}` → `POST ENDPOINTS.ATUNE_ROUTE`.&#x20;
* **Nova triplet:** `propose(brief, headers) → evaluate(candidates) → auction(evaluated, headers)` (always include `x-decision-id`).&#x20;
* **Escalation headers:** `x-decision-id` required; `x-budget-ms` optional.&#x20;

---

## SoC boundaries & invariants

* Evo **never** calls Unity or Synapse directly; Unity is mediated by **Atune** (escalate/route), the market by **Nova**. Keep only `RouterService`, `AtuneClient`, `NovaClient` in scope.&#x20;
* Treat `core.utils.net_api.ENDPOINTS` as **truth**; run SoC lint after overlay changes to avoid `unknown_endpoint`/`illegal_edge`.&#x20;

---

### Governance-aware agents (SoC contracts)

- Any endpoint that drives an LLM **in character** (Nova, Simula, Evo market flows) MUST:
  - Accept `X-Decision-Id` and forward it downstream.
  - Run the **constitutional preamble** (Equor compose) before invoking the model.
  - Emit a **postflight attestation** with the `prompt_patch_id` actually applied.
- Agents **must not** construct prompts by ad-hoc concatenation; they **must** apply the Equor `PromptPatch` surface (pre-composed).
- Failure modes (no active profile, Equor unavailable) are **observed** and **telemetrized**, not silently ignored.

## “Good” looks like (definition of done)

1. `ENDPOINTS` overlay contains all Evo-used keys and URLs; SoC lint green.
2. ObviousnessGate emits calibrated features + score; thresholds logged via telemetry.
3. Every `escalate(...)` writes **ledger**, **replay capsule**, and optionally **scorecard** to Atune.
4. Nova triplet completes with deterministic `decision_id`. &#x20;

---

## Appendix — where to look (repo)

Conflicts (IDs/edges/open list), gate features/threshold & historical fix rate (Cypher), evidence (forecast modality), bridges (RouterService, NovaClient, AtuneClient, SimulaClient).&#x20;

# Equor — canonical guide (scope, identity, KMS, attest, invariants)

## Purpose & role

Equor is the **self-governing identity & governance layer**. It composes deterministic prompt patches from **profiles, facets, and constitutional rules**; validates precedence/conflicts/guard-predicates; monitors **homeostasis** via **attestations**; models/logs internal **qualia** state; and runs **graph-level invariants** to enforce global coherence.&#x20;

---

## Public surface (API routers) — WITH GOVERNANCE PIPELINE

`/equor/*` is mounted from five routers: **attest**, **compose**, **declare**, **drift**, **invariants**.

### Key endpoints (authoritative contracts)
- **POST `/equor/compose`** → deterministic **PromptComposer** from **Profile → {Facets, ConstitutionRules}**, stamps **RCU snapshot**, persists composition metadata; returns `ComposeResponse` with `prompt_patch_id` and `rcu_ref`.
- **POST `/equor/attest`** → accept an `Attestation`, compute coverage (H2+), persist to graph; respond `{status:"accepted", attestation_id}` (202).
- **`/equor/declare`**, **`/equor/drift`**, **`/equor/invariants`** → declare identity/rules, report drift, run invariant checks.

### Governance pipeline (preflight + postflight)
- **Preflight dependency** (`constitutional_preamble`):
  - Requires `X-Decision-Id` for governed calls; calls `/equor/compose` with `{agent, profile_name:"prod", episode_id, context}`.
  - On **200**: attaches `ComposeResponse` to `request.state.constitutional_patch`.
  - On **422/5xx**: warn + proceed without patch (fail-open; policy switchable).
- **Postflight middleware** (`AttestationMiddleware`):
  - If a patch was applied, submits an `Attestation` to `/equor/attest` via background task. `breaches` are inferred from HTTP status (≥400).

### Profiles: storage & mutability
- `(:Profile {agent, name})` with `facet_ids[]`, `rule_ids[]`, and **`settings_json`** (stringified complex config).
- Link edges: `(p)-[:USES_FACET]->(:Facet)` and `(p)-[:APPLIES_RULE]->(:ConstitutionRule)`.

### Compose router invariants
- Ensure `Episode` exists; compute deterministic **`rcu_ref`** from the RCU snapshot; pass `{episode_id, rcu_ref}` into the composer; persist artifacts.

- **Governance first** for identity-sensitive calls; **attest after** every governed action.
- **No ad-hoc prompts**: always apply Equor **PromptPatch**.
- **Header hygiene**: propagate `X-Decision-Id` end-to-end (Evo → Nova → Equor).
- **Graph types**: primitives/arrays only; JSON-encode nested config.
- **Async discipline**: background I/O for non-critical writes (attestations, conflict persistence) to keep the serving path crisp.

---

### Governance pipeline (request preflight + postflight)

**Goal.** Ensure any LLM invocation that requires an “agent identity” runs under an explicit constitutional frame (preflight) and leaves an auditable trail (postflight).

**Preflight (Constitutional Preamble).**
- A FastAPI dependency (`constitutional_preamble`) runs **before** agent endpoints (e.g., `/nova`, `/simula`, `/evo`).
- It expects `X-Decision-Id`. If present, it calls **`POST /equor/compose`** with:
  - `{ agent, profile_name:"prod", episode_id: <X-Decision-Id>, context:{request_path} }`.
- On **200**, it attaches the `ComposeResponse` to `request.state.constitutional_patch` for the handler layer to use.
- On **422** (e.g., no active profile), it logs a warning and **proceeds without a patch** (fail-open with telemetry); the agent call is still allowed to run.
- On transport/500 errors, it logs + proceeds without a patch (configurable to fail-closed later).

**Postflight (Attestation).**
- `AttestationMiddleware` runs **after** the handler returns.
- If a patch was applied (`request.state.constitutional_patch`) and a `X-Decision-Id` was present:
  - It builds an `Attestation` with `{run_id, episode_id, agent, applied_prompt_patch_id, breaches[]}`.
  - `breaches` is empty unless `response.status_code >= 400`.
  - It **submits in the background** to **`POST /equor/attest`** (non-blocking) and never interferes with the main response.

**Headers & contracts.**
- `X-Decision-Id` is **required for governed calls** (same header is already standard for Nova). :contentReference[oaicite:1]{index=1}
- `X-Budget-MS` is optional pass-through for downstream markets (Nova).
- If no header is present, governance is skipped by design (telemetry warns).

**Operational stance.**
- Default **fail-open**: do not block the serving path if compose fails (but log & measure).
- Flip to **fail-closed** by policy when entering stricter compliance modes.

## Canonical data models (message shapes)

* **Facet** — versioned identity text: `{category, version, supersedes}`.&#x20;
* **ConstitutionRule** — `{priority, severity, deontic, predicate_dsl?, supersedes, conflicts_with[]}`.&#x20;
* **Profile** — binds `agent + name` (e.g., `prod`) → `{facet_ids[], rule_ids[]}`.&#x20;
* ### Profiles: storage & mutability (Neo4j)

**Shape.** `(:Profile {agent, name})` binds an identity to concrete **facet** and **rule** selections. Only **primitive types or arrays** are allowed as properties in Neo; store complex settings as **JSON strings**.

**Recommended properties**
- `agent: string` (e.g., "evo")
- `name: string` (e.g., "prod")
- `facet_ids: string[]` (IDs of :Facet)
- `rule_ids: string[]` (IDs of :ConstitutionRule)
- `settings_json: string` (serialized JSON for non-primitive config like `{max_tokens, temperature_cap}`)

**Create / update examples**
```cypher
// 1) Create or upsert the profile
MERGE (p:Profile {agent:$agent, name:$name})
ON CREATE SET p.created_at = datetime()
SET p.facet_ids = $facet_ids,
    p.rule_ids  = $rule_ids,
    p.settings_json = $settings_json  // <- JSON.stringify(settings)

// 2) Explicitly link resolved artifacts (optional but nice for traversal)
UNWIND $facet_ids AS fid
MERGE (f:Facet {id: fid})
MERGE (p)-[:USES_FACET]->(f);

UNWIND $rule_ids AS rid
MERGE (r:ConstitutionRule {id: rid})
MERGE (p)-[:APPLIES_RULE]->(r);
Why JSON? Neo4j only permits primitive values and arrays at property leaves; nested maps like {max_tokens:2000, temperature_cap:0.7} must be stringified to avoid type errors during MERGE. (This keeps the model deterministic while remaining append-only via linking.)

**ComposeRequest / ComposeResponse** — deterministic patch with **checksum**, included IDs, **rcu\_ref**.&#x20;
* **Attestation** — runtime proof of which **PromptPatch** + rules were active; Equor fills `{coverage, breaches[]}` and persists. &#x20;
* **DriftReport / PatchProposalEvent** — homeostasis + corrective proposals.&#x20;
* **Invariant / InvariantCheckResult** — graph invariants + results.&#x20;
* **InternalStateMetrics / QualiaState** — raw internal metrics & 2-D manifold embedding.&#x20;

---

## Identity composition (deterministic, rule-first)

### Router invariants for /equor/compose

- Every compose call **ensures** an `Episode` exists and stamps an **RCU snapshot**; the snapshot is persisted as `(:RCUSnapshot {id:rcu_ref})` with `body` set to a deterministic JSON string.
- `rcu_ref` = `sha256(snapshot_json)[0:24]` prefixed (deterministic, replayable).
- The `ComposeRequest` given to `PromptComposer` **must include** the resolved `episode_id` and the computed `rcu_ref`.
- The `ComposeResponse` contains a `prompt_patch_id` that the Attestation middleware uses later.

`PromptComposer.compose(request, rcu_ref)`:

1. **Lookup** active **Profile** → **Facets + ConstitutionRules** (IdentityRegistry, driverless graph).
2. Apply **rule precedence/conflict** resolution, guard predicates; produce **PromptPatch** + **checksum**; stamp **RCU snapshot**. *(Router wiring shown; full body in Equor core.)* &#x20;

---

## KMS & capability tokens (cross-system MAC)

Equor exposes a minimal HMAC-KMS used by Atune to **mint capability tokens** and by Axon to **validate** them:

* **Keystore**: keys from `EQUOR_KMS_KEYS` (JSON `kid → base64`), else fallback `EQUOR_KMS_K1` (`"k1"`). Helpers: `get_hmac_key_by_kid(kid)`, `get_active_kid()` (env `EQUOR_KMS_ACTIVE_KID`, default `k1`). &#x20;
* **Mint (Atune)**: `_sign_token(intent_id, predicates[], capability, artifact_hash?, version?)` → `{intent_id, signature, predicates, nbf, ...}` using active `kid` & HMAC-SHA256 over `(intent_id + sorted(predicates))`.&#x20;
* **Validate (Axon)**: checks `nbf/exp`, `iss=="equor"`, `aud∈{axon,atune,unity}`, required fields, **capability matches intent**, resolve **KMS key by kid**, **compare HMAC**, and optionally bind to **live driver** `(artifact_hash/version)`.   &#x20;

**Result:** a cross-system MAC that authorizes capabilities + predicate bounds end-to-end (Atune→Axon), with Equor’s KMS as the shared root.&#x20;

---

## Attestation & policy binding

* **Driver attestation (Axon side)**: verify driver `artifact_hash` signed by Equor KMS (`kid`, `signature = HMAC_SHA256(artifact_hash)`), maintain bindings with `AttestationManager`. *(Equor keys consumed via keystore)*. &#x20;
* **Policy attestation (Evo→Equor)**: Evo’s RouterService can call `ENDPOINTS.EQUOR_ATTEST` to verify/persist policy evidence prior to publication.&#x20;

---

## Homeostasis & drift

* **Attestations** represent runs/episodes and include coverage/breaches; Equor persists them (`graph_writes.save_attestation`) and can grow to **HomeostasisMonitor** (H2+).&#x20;
* **Drift reports** track deviation from identity/constitution; **invariants** scan the graph to detect systemic breaches (router and schema placeholders provided). &#x20;

---

## Qualia manifold (internal state modeling)

Equor learns/predicts subjective state trajectories:

* **SelfModel.predict\_next\_state** tries **Synapse-served model** → **historical transition estimator** (Neo) → **identity fallback**; implements **robust mean delta** with **10% tail trimming** before prediction.  &#x20;

---

## Cross-system edges (SoC)

* **Atune → (mint)** capability tokens (Equor KMS) → **Axon (validate)**. &#x20;
* **Evo → Equor** (policy attestation) before publishing attention bids.&#x20;
* **Unity** may **veto** verdicts that breach **Equor constitution** (adjudicator check), keeping governance centralized in Equor’s ruleset.&#x20;

---

## Minimal contract examples (ground-truth)

* **Attest** → body: `Attestation{episode_id, run_id, profile_id, patch_id, rules[], coverage?, breaches[]}`; resp: `{status:"accepted", attestation_id}`.&#x20;
* **Compose** → body: `ComposeRequest{profile_id, context, rcu_ref?}`; resp: `ComposeResponse{patch, checksum, included_ids, rcu_ref}`. &#x20;
* **Capability token** (minted by Atune): `{intent_id, signature, predicates[], nbf, ... , kid}`; **Axon** must see `iss:"equor"`, `aud ∈ {axon, atune, unity}`, and matching `capability`. &#x20;

---
### Escalation stack — implementation notes

**Conflict intake & hydration**
- `/evo/escalate` accepts `{conflict_ids[]}` (plus legacy `conflict_id` or `conflicts[]` nodes) and **hydrates** any unknown IDs from Neo4j by `conflict_id|id|event_id`.
- Hydration normalizes: `severity ∈ {low|medium|high|critical}`, `kind ∈ {failure|degradation|anomaly|violation}`, `t_created` (sec), and `context.modules` (list).
- Unknown IDs → **404** with `{unknown_conflict_ids: [...]}`.

**In-memory store + background persistence**
- `ConflictsService.batch()` updates RAM and schedules a background **MERGE**:
  ```cypher
  UNWIND $rows AS row
  MERGE (c:Conflict { conflict_id: row.id })
  SET c += row.props

Nodes carry safe defaults (e.g., spec_coverage:{has_spec:false,gaps:[]}, embedding:[]) so feature extractors never crash.

ObviousnessGate

Async scoring gathers per-conflict features (spec_present, spec_gaps, reproducer_stable, locality, severity) and a graph-derived historical_fix_rate.

If obvious: short-circuit to local repair (planned path).

If not obvious: escalate to Nova triplet with x-decision-id and optional x-budget-ms.

Nova error handling

Even if Nova is unavailable, escalate() returns a schema-valid result:

candidates: []

auction: { winners:[], spend_ms:0, market_receipt:{error:"..."} }

provenance.error includes the traceback for ops.

## Readiness checklist (what “good” looks like)

1. **Keystore** env set (`EQUOR_KMS_KEYS` or `EQUOR_KMS_K1` + `EQUOR_KMS_ACTIVE_KID`). &#x20;
2. **Attest** path wired; attestations persist to graph.&#x20;
3. **Compose** path returns deterministic patches with checksum + RCU stamp.&#x20;
4. **Axon** validates Equor tokens; **Evo** can call `EQUOR_ATTEST`. &#x20;
5. **Unity adjudicator** ties verdict approvals to constitution checks.&#x20;

# Nova — canonical guide (market, endpoints, runners, handoff, artifacts)

## Purpose & role

Nova is the **invention market**. It accepts an **InnovationBrief**, generates **InventionCandidates** via playbooks, evaluates them, and runs an **auction** to select winners. The contract is the triplet **`propose → evaluate → auction`**, with deterministic tracing via headers. Evo talks to Nova only through `NOVA_{PROPOSE,EVALUATE,AUCTION}`. &#x20;

---

## Public surface (routers & wiring)

FastAPI router group **`api/endpoints/nova/*`** mounts:

* **core** (market + artifacts),
* **handoff** (winner→Simula patch),
* **policy** (capability proofs/validation),
* **winner** (prepare a patch from a chosen auction result).&#x20;

Core services in this router: **PlaybookRunner**, **EvalRunner**, **AuctionClient**, **RolloutClient**, **ProofVM**, **SynapseBudgetClient**, **NovaLedger**.&#x20;

---

## Market triplet (authoritative contracts)

### POST `/nova/propose` → `List[InventionCandidate]`

* Input: `InnovationBrief` (pydantic).
* Budgeting: if `x-budget-ms` missing/zero, Nova consults **SynapseBudgetClient** to allocate a budget.
* Headers echoed: if `x-decision-id` provided, Nova returns `X-Decision-Id`.
* Body: list of candidates from playbooks (bounded by allocated budget). &#x20;

### POST `/nova/evaluate` → `List[InventionCandidate]`

* Input: candidates; Output: candidates with evaluation results (tests/logs attached by **EvalRunner**).&#x20;

### POST `/nova/auction` → `AuctionResult`

* Input: evaluated candidates; Output: winners + **market receipt**.
* Headers returned: `X-Decision-Id` (if supplied) and **`X-Market-Receipt-Hash`** (stable hash for WhyTrace joins).&#x20;

**Client usage (Evo → Nova):** Evo’s `NovaClient` posts to `ENDPOINTS.NOVA_{PROPOSE,EVALUATE,AUCTION}`; always sends `x-decision-id`, and passes `x-budget-ms` where relevant. &#x20;

---

## Winner handoff (to patching)

### `winner/prepare`

Select the top auction winner and return a **SimulaPatchBrief** (preview only; no submission). Input: `{brief, candidates, auction, env_pins?, seeds?}`. Echoes `X-Decision-Id` when provided. &#x20;

### `handoff/patch/prepare` and `handoff/patch/submit`

* **prepare**: build a `SimulaPatchBrief` for a given `{brief, winner}`.
* **submit**: send a `SimulaPatchBrief` to Simula; returns a `SimulaPatchTicket`. Both stamp `X-Decision-Id` if provided. &#x20;

---

## Artifacts, proofs, rollout

### Design capsules (ledger)

* **POST `/nova/capsule/save`** persists a **DesignCapsule** `{brief, artifacts, playbook_dag, eval_logs, counterfactuals, costs, env_pins, seeds}` and returns it with header **`X-DesignCapsule-Hash`** (blake2s over sorted JSON).&#x20;

* **GET `/nova/archive/{capsule_id}`** returns a stored capsule. **GET `/nova/playbooks`** lists available playbooks.&#x20;

### Policy/Proofs

* **POST `/nova/proof/check`** runs **ProofVM** over `{capability_spec, obligations, evidence?}`; returns `ProofResult`.&#x20;

* **POST `/nova/policy/validate`** forwards `{capability_spec, obligations, identity_context}` to **EquorPolicyClient**; response is Equor’s decision.&#x20;

### Rollout

* **POST `/nova/rollout`** executes a rollout plan (`RolloutRequest`) through **RolloutClient** and returns `RolloutResult`.&#x20;

---

## Observability & headers

Nova consistently stamps **`X-Cost-MS`** (wall time). On calls carrying `x-decision-id`, the response includes **`X-Decision-Id`**. Auctions add **`X-Market-Receipt-Hash`**. These appear across core endpoints.  &#x20;

---

## Data models (Nova side: referenced)

API surfaces the following pydantic models from `systems.nova.schemas`: **InnovationBrief**, **InventionCandidate**, **AuctionResult**, **DesignCapsule**, **RolloutRequest/Result**. They are the request/response shapes for the routes above.&#x20;

---

## SoC edges & contracts

* **Evo ↔ Nova** only via `NOVA_{PROPOSE,EVALUATE,AUCTION}`; Evo must provide `x-decision-id` and optional `x-budget-ms`. &#x20;
* **Nova ↔ Synapse** used **internally** to allocate a budget if caller omits one.&#x20;
* **Nova ↔ Equor** via `/policy/validate` when capability checks are requested.&#x20;
* **Nova ↔ Simula** through **handoff** routes producing/submitting a `SimulaPatchBrief/Ticket`. &#x20;

---

## Minimal reference flow

1. **propose**(brief, headers: `x-decision-id`, `x-budget-ms?`) → candidates.
2. **evaluate**(candidates) → evaluated candidates.
3. **auction**(evaluated, headers) → `AuctionResult` + `X-Market-Receipt-Hash`.
4. **winner/prepare** or **handoff/patch/prepare** → `SimulaPatchBrief`; optional **handoff/patch/submit**.   &#x20;

---

## “Good” looks like (definition of done)

* `ENDPOINTS` overlay exposes **`NOVA_{PROPOSE,EVALUATE,AUCTION}`** (and Evo’s `NovaClient` uses only those).
* Calls carry `x-decision-id`; responses stamp `X-Decision-Id` and, for auctions, `X-Market-Receipt-Hash`.
* Handoff path produces a valid **SimulaPatchBrief** and can submit to Simula.
* Capsules saved with `X-DesignCapsule-Hash`; playbooks and proofs endpoints responsive.  &#x20;

# Qora + Synk — canonical guide (tooling/catalog + switchboard/graph/semantic)

## Purpose & role

* **Qora**: system tool **catalog + search + schema + execution** for functions decorated with `@eos_tool`. Provides a stable HTTP contract used by Simula, Atune, Axon drivers, Unity protocols, and offline tooling.
* **Synk**: runtime **Switchboard** (feature flags & rollout gating) and **driverless Neo4j + vector** toolkit (schema bootstrap, semantic search, idempotent writes, conflict nodes, simple embedding defaults).

### Conflict nodes: embeddings & Evo patrol

- `create_conflict_node(system, description, origin_node_id, additional_data?)` now:
  - Computes a **3072-dim** embedding (Gemini RETRIEVAL_DOCUMENT) from `additional_data.goal || description` and writes it into `:Conflict.embedding`.
  - Stores `additional_data` in `:Conflict.context` for richer downstream analysis.
  - Notifies Evo Patrol best-effort by posting `{conflict_id, description, tags?}` to `/evo/escalate`. (Failures logged; conflict still persists.)

**Note.** All vector settings (model, dims) are driven by the global embedding defaults; see “Embedding defaults” under Synk. 

---

## Qora — public surface (alias keys only)

* `QORA_ARCH_SEARCH` — POST `/qora/arch/search` → ranked tool candidates (`query, safety_max, system?, top_k`).
* `QORA_ARCH_SCHEMA` — GET `/qora/arch/schema/{uid}` → parameter/output schemas, `safety_tier`, `allow_external`.
* `QORA_ARCH_EXECUTE_BY_UID` — POST `/qora/arch/execute-by-uid` → run a specific tool by `uid` with `args`.
* `QORA_ARCH_EXECUTE_BY_QUERY` — POST `/qora/arch/execute-by-query` → search then execute top candidate.
* `QORA_TOOLS_CATALOG` — GET `/qora/catalog` → list tools (filters: `agent`, `capability`, `safety_max`).
* `QORA_ARCH_HEALTH` — GET `/qora/arch/health` (optional; used by drivers for self-test).

**Security:** all `/qora/arch/*` require `X-Qora-Key` (client populates from `QORA_API_KEY|EOS_API_KEY`).

---

## Qora — canonical data & behavior

* **Tool metadata source**: `@eos_tool` decorator (`name, description, inputs, outputs, agent, capabilities, safety_tier, allow_external`).
* **Patrol ingestion**: scans code for decorated functions, computes `uid = blake2b(module:qualname)`, upserts `(:SystemFunction {uid})` with fields `tool_name/desc/agent/capabilities/safety_tier/allow_external/module/qualname/schemas`.
* **Search**: hybrid text over catalog fields (+ filters: `safety_tier ≤ safety_max`, `agent?`, `capability?`), returns `uid + schema summary`.
* **Schema**: returns full parameter/output schema for a given `uid`.
* **Execute-by-uid**:

  1. fetch meta; **policy gates**: reject when `safety_tier` exceeds caller’s bound; deny external arguments when `allow_external == false` (simple URL/SSH heuristics).
  2. dynamic import `module.qualname` → call; await if coroutine.
  3. log `(:ToolRun)-[:RAN]->(:SystemFunction)` with duration, caller, ok/error.
* **Execute-by-query**: `search → execute-by-uid` fast path (same gates/logging).
* **AuthN/headers**: require `X-Qora-Key`; echo decision headers if present (for tracing).

**Client helpers (internal callers):**
`fetch_llm_tools`, `qora_search`, `qora_schema`, `qora_exec_by_uid`, `qora_exec_by_query` (always set `X-Qora-Key`).

---

## Qora — SoC edges

* **Simula**: uses search/exec to run system tools (fast path) or validate-by-UID (strict path) inside code-evolution loops.
* **Axon**: `qora:search` driver calls **execute-by-query**; `self_test()` hits **arch/health**.
* **Atune/Unity/Equor**: may browse catalog or invoke specific tools via clients; all paths go through Qora HTTP (no direct imports).

---

## Synk — Switchboard (feature flags)

* **In-process TTL cache** of `(:Flag {key, value_json|default_json})` with prefix-sliced refresh and double-checked locking; `TTL=0` = refresh each call.
* **API (typed)**: `get(key) → Any | default`, `get_bool/int/float`, `require_flag_true("ns.flag")` (FastAPI dependency, returns 403 when false), `gate(flag_key)` boolean, plus route/func-gate wrappers (with optional jitter/backoff).
* **Best practice**: namespace flags (e.g., `atune.market.*`, `simula.sandbox.*`) for cache-efficient refresh; keep defaults stable and documented.

---

## Synk — driverless Neo4j & vector toolkit

* **Schema bootstrap**: create constraints/indexes for core labels (e.g., `Event`, `Tool`, `Cluster`); ensure **Neo4j 5 vector indexes** (ANN) exist (defaults: `label="Event"`, `prop="vector_gemini"`, `dims=3072`).
* **Vector store manager**: helpers to `create_vector_index`, map label→index, and query.
* **Semantic search**: `semantic_graph_search(text, top_k, labels?)` → queries `db.index.vector.queryNodes` per label, merges/dedupes results; returns `[{id, score, props}]`.
* **Idempotent writes**: `add_node(labels, props, embed_text?)` merges by stable keys (`fqn+hash` | `name+system` | `event_id`), timestamps, optional **embed→write vector**.
* **Conflict nodes**: `create_conflict_node(...)` (used by Evo); optional webhook to Evo Patrol.
* **Embedding defaults**: config resolved **Neo → ENV → fallback**; **dimensions hard-locked @ 3072**; cached with TTL.

---

## Synk — SoC edges

* **Used by** Simula/Atune/Evo/Unity for graph writes and semantic lookups via **driverless helpers** (no direct driver sessions in app code).
* **Switchboard gating** wraps routes/loops/daemons across systems for **rollout** and **kill-switches**.

---

## Operational knobs (illustrative)

* **Qora**: `X-Qora-Key` env (`QORA_API_KEY|EOS_API_KEY`); search `top_k` cap; default `safety_max` for callers; logging level for Patrol.
* **Synk**: `SWITCHBOARD_TTL_SEC`, optional `SWITCHBOARD_NS_PREFIX` filters; vector index dims (fixed 3072), label→index map; embedding model (`gemini-embedding-001` by default); ANN similarity score floors per label.

---

## Minimal payload shapes (reference)

* **/qora/arch/search**: `{ "query": str, "top_k"?: int, "safety_max"?: int, "system"?: str }` → `{ "candidates": [{ "uid": str, "tool_name": str, "agent": str, "capabilities": [str], "safety_tier": int }] }`
* **/qora/arch/schema/{uid}**: → `{ "uid": str, "inputs": {...json schema...}, "outputs": {...}, "safety_tier": int, "allow_external": bool, "module": str, "qualname": str }`
* **/qora/arch/execute-by-uid**: `{ "uid": str, "args": {...} }` → `{ "ok": bool, "result": Any, "duration_ms": int, "uid": str }`
* **/qora/arch/execute-by-query**: `{ "query": str, "args": {...}, "top_k"?: int, "safety_max"?: int, "system"?: str }` → same as execute-by-uid

---

## Definition of done (for this chapter)

1. Overlay exposes **all Qora alias keys** above; clients send **`X-Qora-Key`**; `arch/*` routes enforce it.
2. Patrol populates catalog from code; `/qora/catalog` lists decorated tools with schemas/safety flags.
3. `execute-by-uid/query` enforce **safety tier** and **external-access** policy; runs are logged to graph.
4. Synk Switchboard guards critical paths; TTL/namespace confirmed.
5. Driverless graph utilities usable from all systems; **vector indexes** exist with **dims=3072**; `semantic_graph_search` returns stable results across labels.

# Core — canonical guide (overlay, LLM bus, embeddings, event bus, ops)

## Purpose & role

The **Core** layer provides infra contracts used by higher systems: the **OpenAPI → alias overlay (`ENDPOINTS`)**, the **LLM bus** (provider-agnostic call surface + tool-spec translations), **embeddings service (Gemini, 3072-dim hard-lock)**, an async **EventBus**, and standard **env/operational knobs**. It explicitly avoids embedding business logic from Synapse/Equor/Atune/Simula.&#x20;

---

## OpenAPI overlay → `ENDPOINTS` (net\_api)

* **Mechanics.** Fetch `OPENAPI_PATH`, extract `paths`, then: (1) upgrade fallback aliases by best-suffix, (2) derive aliases for **all** paths (e.g., `/simula/jobs/codegen` → `SIMULA_JOBS_CODEGEN`). Public API: dynamic `ENDPOINTS.KEY` (metaclass), `endpoints.path(name, **params)`, resolvers `QORA_SCHEMA_UID(key)` / `SYNK_FLAG_GET(key)`, and `endpoints_snapshot()`. Params formatting accepts `{k}` or `:k`. **SoC:** systems **must not** hardcode URLs—use `ENDPOINTS.*` + `get_http_client()`.&#x20;

* **Operational knobs.** `ECODIAOS_BASE_URL`, `ECODIAOS_HTTP_TIMEOUT`, `OPENAPI_PATH`, `ENDPOINTS_POLL_SEC`, `ENDPOINTS_DEBUG`. Overlay never raises on fetch errors; debug logs counts; unknown alias access raises `AttributeError`. &#x20;

---

## LLM bus (provider-agnostic)

* **Scope.** `core/llm/call_llm.py` exposes a single call surface with policy-driven `model/temperature/max_tokens` (not hardcoded). It explicitly **removes Synapse/Equor imports**; only formatting and providers remain. **Env knob:** `LLM_BUS_NETWORK_TIMEOUT`. &#x20;

* **Message & JSON hygiene.** Helpers sanitize roles/content and robustly parse JSON (including fenced blocks and substring recovery). &#x20;

* **Provider routing.** Model name → provider mapping (`claude`→Anthropic, `gpt`→OpenAI, `gemini`→Gemini; `google` normalized to `gemini`). &#x20;

* **Tool-spec translations.** Unified `ToolSpec{name,description,parameters,returns}` mapped to each SDK:

  * OpenAI: `{"type":"function","function":{...}}`
  * Anthropic: `{name,description,input_schema}`
  * Gemini: `{"function_declarations":[...]}`
    Includes provider-specific `tool_choice` mapping (`auto|none|<name>`).  &#x20;

* **Correct usage pattern.** Build prompts with the orchestrator, then call via **event bus** (`llm_call_request/llm_call_response`) or direct core bus helpers (`_llm_call`/`execute_llm_call`); validate to schema; enable `auto_repair` only when a schema exists.&#x20;

---

## Embeddings service (Gemini, 3072-dim)

* **Contract.** Local-first env load (`ENV_FILE` → workspace `.env` → `D:\EcodiaOS\config\.env`), requires **`GOOGLE_API_KEY`**, client via `google-genai`, model from `GEMINI_EMBEDDING_MODEL` (fallback `gemini-embedding-001`). **Hard-lock to 3072 dims** with loud runtime assertions; Neo4j-backed defaults with TTL cache; async-safe batching and retries.&#x20;

* **Runtime checks.** Batch path verifies every vector length equals **3072**; includes a startup **sanity probe** (optional) printing model/task/dims and vector length. &#x20;

* **Env bootstrap helper.** Centralized `.env` loader gives priority to `ENV_FILE`, then workspace discovery, then canonical Windows path.&#x20;

* **Downstream defaults.** Synk’s Vector Store uses **dims=3072**, ANN cosine indexes (`Event.vector_gemini`, `Cluster.cluster_vector_gemini`).&#x20;

---

## Event bus (system-wide async pub/sub)

* **Implementation.** Singleton `EventBus` with `subscribe(event_type, callback)` and `publish(event_type, **kwargs)` (fan-out with `asyncio.gather`). Publishes with no subscribers just log and return. Used across systems for decoupled flows.  &#x20;

---

## Operational knobs & failure modes

* **Env knobs recap.** `ECODIAOS_BASE_URL`, `ECODIAOS_HTTP_TIMEOUT`, `OPENAPI_PATH`, `ENDPOINTS_POLL_SEC`, `ENDPOINTS_DEBUG`; LLM: `LLM_BUS_NETWORK_TIMEOUT`; prompts: `EOS_PROMPT_SPECS`, `EOS_TEMPLATES_PATH`; embeddings: `GOOGLE_API_KEY`, `GEMINI_EMBEDDING_MODEL`.&#x20;

* **Guardrails.** Overlay keeps fallbacks on fetch errors; unknown endpoint raises `AttributeError`. Prompt rendering inserts inline error markers for missing partials. Schema-validation errors are captured; **auto-repair** bounded (low tokens/temp). LLM provider errors bubble as `{ok:false,error,duration_ms}` and then as a bus-level `{error}` envelope.&#x20;

---

## SoC boundaries & contributor checklist

* **Core does not** decide policy (Synapse), identity/affect (Equor/Atune), or codegen/testing (Simula); it **exposes** infra they consume. **Checklist:** define prompts via `PromptSpec` (with schemas/partials), render with provenance, call LLMs via bus or core helpers (not raw SDKs), resolve URLs only through `ENDPOINTS`, and use `embeddings_gemini` for vectors.&#x20;

---

## Minimal references (for consumers)

* **Overlay status:** `GET /meta/endpoints` (JSON snapshot) and `/meta/endpoints.txt` (formatted). Use these to verify which aliases are live.&#x20;
* **Origin ingestion (API facet exposed by core app):** admin-gated `/origin/{node|edges|search|batch_csv}` with startup index ensure. *(For completeness of the final guide’s “API” chapter.)*&#x20;
# API — canonical guide (app topology, routes, headers, auth, behaviors)

## App topology

* **Framework:** FastAPI app with routers per domain: `/atune/*`, `/axon/*`, `/nova/*`, `/equor/*`, `/qora/*`, `/synapse/*` (where present), plus **health/meta** and **origin** ingestion surfaces.
* **Meta/Health:**

  * `GET /` → `"ok"`
  * `GET /health` → `{ok:true}` (200) or `{ok:false,error}` (non-200)
  * `GET /neo` → driverless `RETURN 1 AS ok`
  * `GET /vector` → Neo4j 5 index check (falls back to legacy)
  * `GET /meta/endpoints` → JSON overlay snapshot (**authoritative alias→path map**)
  * `GET /meta/endpoints.txt` → human-formatted overlay report

---

## Global headers & tracing (used across domains)

* **Request (ingress):**

  * `x-decision-id` (UUID-like; correlates Atune↔Axon↔Unity↔Evo↔Nova)
  * `x-budget-ms` (integer milliseconds budget envelope)
* **Response (egress):**

  * `X-Cost-MS` (wall time used)
  * Domain-specific: `X-Decision-Id` (echo), `X-Market-Receipt-Hash` (Nova auctions), `X-DesignCapsule-Hash` (Nova capsules)

---

## Atune (attention & planning)

* `POST /atune/route` — single event route. Body: `{"event": {...}, "affect_override"?: {...}}`.
* `POST /atune/cognitive_cycle` — batch route. Body: `{"events": [...], "affect_override"?: {...}}`.
* `POST /atune/escalate` — Unity bridge (see “Unity bridge schema” below). Requires/accepts `x-budget-ms`.
* `GET /atune/trace/{decision_id}` — WhyTrace + ReplayCapsule bundle.
* `GET /atune/meta/status` — budget pool, leak-gamma, AB toggles, SECL counters.
* **Headers:** always send `x-decision-id`; Atune forwards it to Axon/Unity; replies include `X-Cost-MS`.

### Unity bridge schema (Atune <-> Unity)

* **Request body:** `{ episode_id, reason, intent, predicted_result, predicted_utility, risk_factors, rollback_options, context }`
* **Response body:** `{ status: "approve_with_edits" | "reject" | "request_more_context" | "no_action", edits?: {...} }`
* **Headers:** `x-budget-ms` honored; decision id propagated.

---

## Axon (action layer)

* `POST /axon/core/act` — execute an `AxonIntent`. Resp: `ActionResult`; header `X-Cost-MS`. Validates **Equor capability token**.
* `POST /axon/ab/run` — twin + shadows dry-run for the same intent. Resp: `{ twin, shadows: [...] }`.
* `GET /axon/mesh/capabilities` — current capability registry (testing/shadow/live). Used by Atune for discovery/KG seeding.

### Probecraft (capability lifecycle)

* `POST /axon/probecraft/drivers/{driver_name}/status` — set driver status (`testing|shadow|live`); may dynamically load/register.
* `POST /axon/probecraft/synthesize` — synthesize a driver from an OpenAPI spec URL (artifact generation + registration).
* *(If mounted)* `POST /axon/probecraft/intake` — intake from Atune **CapabilityGapEvent** (spec/discovery → playbook/rollback merge → AB kickoff).

**Axon → Atune follow-ups:** best-effort `action.result` / `search.results` to `/atune/route` or `/atune/cognitive_cycle` with `x-decision-id` (+ optional `x-budget-ms`).

---

## Nova (innovation market)

* `POST /nova/propose` — input `InnovationBrief`; output `InventionCandidate[]`. If `x-budget-ms` absent, Nova consults **Synapse budget**.
* `POST /nova/evaluate` — evaluate candidates; returns enriched candidates.
* `POST /nova/auction` — run auction; returns `AuctionResult`; headers: `X-Decision-Id`, `X-Market-Receipt-Hash`.
* **Winner/Handoff:**

  * `POST /nova/winner/prepare` — produce `SimulaPatchBrief` from top winner (preview).
  * `POST /nova/handoff/patch/prepare` — brief for a chosen winner.
  * `POST /nova/handoff/patch/submit` — submit patch brief to Simula; returns `SimulaPatchTicket`.
* **Artifacts/Proofs/Rollout:**

  * `POST /nova/capsule/save` (returns `X-DesignCapsule-Hash`), `GET /nova/archive/{id}`, `GET /nova/playbooks`
  * `POST /nova/proof/check` (ProofVM), `POST /nova/policy/validate` (Equor policy)
  * `POST /nova/rollout` (execute rollout plan)

---

## Qora (tool catalog & execution)

* `GET /qora/catalog` — list tools (filters: `agent, capability, safety_max`).
* `POST /qora/arch/search` — search tools.
* `GET /qora/arch/schema/{uid}` — parameter/output schemas + safety flags.
* `POST /qora/arch/execute-by-uid` — execute by uid.
* `POST /qora/arch/execute-by-query` — search-then-execute fast path.
  **Auth:** all `/qora/arch/*` require `X-Qora-Key` (clients populate from `QORA_API_KEY|EOS_API_KEY`).

---

## Equor (identity, KMS, attestations, invariants)

* `POST /equor/compose` — deterministic `PromptPatch` from `Profile` (facets + rules); returns `{patch, checksum, included_ids, rcu_ref}`.
* `POST /equor/attest` — persist `Attestation` (coverage + breaches); returns `{status:"accepted", attestation_id}` (202).
* `POST /equor/declare` — declare profiles/facets/rules (admin/developer-only contexts).
* `POST /equor/drift` — report drift from identity/homeostasis baselines.
* `POST /equor/invariants` — run invariant checks and return results.

---

## Synapse (policy hub; if routed via API)

* Canonical operations (when exposed): `select_arm`, `simulate`, `smt_check`, `budget`, `explain`, `log_outcome`, `preference_ingest`, `continue_option`, `repair_skill`, `registry_reload` (external callers only; internal reload should be in-proc).
* Expectation: all routes map 1:1 to `ENDPOINTS.SYNAPSE_*` aliases for overlay parity.

---

## Synk (switchboard & driverless graph; if exposed)

* Feature-flag **deps** for route gating: `require_flag_true("ns.flag")`.
* Admin/ops-only endpoints where present for flag snapshots or schema bootstrap.

---

## Origin (graph-first ingestion utilities)

* **Admin-gated** (`X-Admin-Token`, loaded at startup from `ADMIN_API_TOKEN`):

  * `POST /origin/node` — create `:Origin` node `{title,summary,what,where,when,tags}`.
  * `POST /origin/edges` — create edges from `from_id` to `{to_id,label,note}[]` (supports `@alias:` resolution per batch).
  * `POST /origin/search` — mixed search across ids/labels/title/summary (top-k).
  * `POST /origin/batch_csv` — two-pass CSV (create nodes → edges) with aliasing; returns `{created, edges_created, errors[], aliases{}}`.
* **Startup:** ensures required indexes/constraints.

---

## Auth & safety

* **Admin scope:** Origin endpoints require `X-Admin-Token`. Missing token → clear 401/403 or 500 with hint (depending on bootstrap path).
* **Qora scope:** `/qora/arch/*` requires `X-Qora-Key`; 401 on missing/invalid.
* **Equor/Axon:** Axon validates **Equor** capability tokens (HMAC `kid`, `iss:"equor"`, `aud∈{axon,atune,unity}`, capability/predicate match).
* **Budget discipline:** Many routes **require/propagate** `x-budget-ms`; all flows should **echo `X-Cost-MS`**.

---

## Overlay parity (critical for lint)

* Every in-code alias reference (e.g., `ENDPOINTS.ATUNE_ROUTE`, `AXON_ACT`, `NOVA_PROPOSE`, `QORA_ARCH_EXECUTE_BY_QUERY`, `SIMULA_*`, `EQUOR_*`, `SYNAPSE_*`) **must** appear in `/meta/endpoints` with **non-fallback** source.
* Unknown/missing aliases are the root cause of **\[unknown\_endpoint]** and **\[illegal\_edge]** lint errors; the app exposes `/meta/endpoints(.txt)` to audit what’s live.

---

## Example request snippets (reference)

### Atune route (single event)

```
POST /atune/route
Headers: x-decision-id: <uuid>, x-budget-ms: 2500
Body: { "event": {...}, "affect_override": {...?} }
```

### Axon act

```
POST /axon/core/act
Headers: x-decision-id: <uuid>, x-budget-ms: 1500
Body: { "capability": "qora:search", "params": {...}, "constraints": {...}, "policy_trace": {...},
        "rollback_contract": {...?}, "equor_token": {...} }
Resp headers: X-Cost-MS: <ms>
```

### Nova auction

```
POST /nova/auction
Headers: x-decision-id: <uuid>
Body: { "candidates": [...evaluated...] }
Resp headers: X-Decision-Id: <uuid>, X-Market-Receipt-Hash: <hash>
```

### Qora execute-by-uid

```
POST /qora/arch/execute-by-uid
Headers: X-Qora-Key: <key>, x-decision-id: <uuid?>
Body: { "uid": "<tool-uid>", "args": {...} }
```

### Equor attest

```
POST /equor/attest
Body: { "episode_id": "...", "profile_id": "...", "patch_id": "...", "rules": [...], "coverage": {...}, "breaches": [...] }
```

### Origin batch CSV

```
POST /origin/batch_csv
Headers: X-Admin-Token: <token>
Body: { "csv": "title,summary,what,where,when,tags,edges,alias\n..." }
```

---

## Definition of done (API chapter)

1. `/meta/endpoints(.txt)` shows **all** aliases used by systems with correct paths; no fallbacks left for in-repo services.
2. Health endpoints (`/health`, `/neo`, `/vector`) return **200** in CI.
3. Atune↔Axon↔Unity flows preserve `x-decision-id`, honor `x-budget-ms`, and stamp `X-Cost-MS`.
4. Qora `/arch/*` enforce `X-Qora-Key`.
5. Origin routes gated by `X-Admin-Token`, with CSV two-pass semantics and error accumulation.
