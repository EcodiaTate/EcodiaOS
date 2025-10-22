from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from typing import Any, Dict, List, Optional

# Use the shared embedding helper (3072-d Gemini)
from core.llm.embeddings_gemini import get_embedding
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from core.utils.neo.cypher_query import cypher_query

from .schemas import ErrorEventIngest

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Tunables (env/pluggable via future settings.py)
# ──────────────────────────────────────────────────────────────────────────────
EMBED_MODEL = "gemini-embedding-001"
SIM_T1_CLUSTER = 0.84
SIM_T2_MERGE = 0.80
PROMOTE_MIN_T1 = 2
PROMOTE_MIN_T2 = 2
TOPK_INJECT = 6
HALF_LIFE_DAYS = 30


# ──────────────────────────────────────────────────────────────────────────────
# Embedding helpers (doc vs. query + multi-query compose)
# ──────────────────────────────────────────────────────────────────────────────
async def _embed_doc(text: str) -> list[float]:
    """Embedding for stored content (Advice nodes)."""
    return await get_embedding(text, task_type="RETRIEVAL_DOCUMENT", model=EMBED_MODEL)


async def _embed_query(q: str | Sequence[str]) -> list[float]:
    """
    Embedding for retrieval queries; supports a single string OR a list of strings.
    If a list is provided, returns the element-wise mean (robust multi-hint query).
    """
    if isinstance(q, str):
        return await get_embedding(q, task_type="RETRIEVAL_QUERY", model=EMBED_MODEL)

    # multi-query: mean pooling (element-wise)
    vecs: list[list[float]] = []
    for part in q:
        if not part:
            continue
        v = await get_embedding(part, task_type="RETRIEVAL_QUERY", model=EMBED_MODEL)
        vecs.append(v)
    if not vecs:
        # fallback: embed an empty query safely
        return await get_embedding("", task_type="RETRIEVAL_QUERY", model=EMBED_MODEL)

    dim = len(vecs[0])
    acc = [0.0] * dim
    for v in vecs:
        # defensive: ensure consistent dims
        if len(v) != dim:
            raise RuntimeError(
                f"[ADVICE] Inconsistent embedding dims; expected {dim}, got {len(v)}",
            )
        for i in range(dim):
            acc[i] += v[i]
    n = float(len(vecs))
    return [x / n for x in acc]


class AdviceEngine:
    """Core ingest→cluster→synthesize→merge→retrieve→reward/decay engine."""

    def __init__(self, embed_model: str = EMBED_MODEL):
        self.embed_model = embed_model

    # ------------------------------------------------------------------ T1 CAPTURE

    async def ingest_error(self, e: ErrorEventIngest) -> str:
        """Create a level-1 Advice node from a concrete error event (T1)."""
        text = self._compose_t1_text(e)
        vec = await _embed_doc(text)
        rows = await cypher_query(
            """
            WITH $e AS e, $vec AS emb
            MERGE (ev:ErrorEvent {id: e.turn_id})
              ON CREATE SET ev += e, ev.created_at = timestamp()
            CREATE (a:Advice {
                id: randomUUID(),
                level: 1,
                kind: 'code_advice',
                text: e.message,
                checklist: [],
                donts: [],
                validation: [],
                scope: [x IN [e.symbol, e.file] WHERE x IS NOT NULL],
                weight: 1.0,
                sim_threshold: $t1_thr,
                occurrences: 1,
                last_seen: timestamp(),
                impact: 0.0,
                embedding: emb
            })
            CREATE (a)-[:DERIVED_FROM]->(ev)
            FOREACH (m IN CASE WHEN e.symbol IS NULL THEN [] ELSE [e.symbol] END |
              MERGE (s:Symbol {fqname: m})
              MERGE (a)-[:APPLIES_TO]->(s)
            )
            FOREACH (p IN CASE WHEN e.file IS NULL THEN [] ELSE [e.file] END |
              MERGE (m:Module {path: p})
              MERGE (a)-[:APPLIES_TO]->(m)
            )
            RETURN a.id AS id
            """,
            {"e": e.model_dump(mode="json"), "vec": vec, "t1_thr": SIM_T1_CLUSTER},
        )
        if not rows:
            raise RuntimeError("AdviceEngine.ingest_error: no row returned from Cypher")
        return rows[0]["id"]

    def _compose_t1_text(self, e: ErrorEventIngest) -> str:
        return (
            f"{e.message}\n"
            f"Tags:{' '.join(e.tags)}\n"
            f"File:{e.file}\n"
            f"Symbol:{e.symbol}\n"
            f"Diff:\n{e.diff}\n"
            f"Context:\n{e.context_snippet or ''}"
        )

    # ------------------------------------------------------------- CLUSTER / MATCH

    async def match_similar_t1(self, advice_id: str, topk: int = 12) -> list[dict[str, Any]]:
        rows = await cypher_query(
            """
            MATCH (a:Advice {id:$id, level:1})
            CALL db.index.vector.queryNodes('advice_embedding_idx', $k, a.embedding) YIELD node, score
            WHERE node.level = 1 AND node.id <> a.id
            RETURN node.id AS id, score, node.text AS text, node.scope AS scope
            ORDER BY score DESC
            """,
            {"id": advice_id, "k": topk},
        )
        return rows or []

    # -------------------------------------------------------------- T2 SYNTHESIS

    async def synthesize_t2(self, seed_id: str) -> str | None:
        """
        Merge a cluster of similar T1 incidents into an enforceable T2 Advice doc
        using the prompt spec scope `simula.advice.synth_t2`.
        """
        cluster = await self.match_similar_t1(seed_id)
        strong = [c for c in (cluster or []) if float(c.get("score", 0.0)) >= SIM_T1_CLUSTER]
        if len(strong) + 1 < PROMOTE_MIN_T1:
            return None

        t1_payloads = await self._fetch_t1_payloads([seed_id] + [c["id"] for c in strong])
        prompt = await build_prompt(
            scope="simula.advice.synth_t2",
            context={"incidents": t1_payloads},
            summary="Merge repetitive incidents into generalized, enforceable advice (strict JSON).",
        )
        resp = await call_llm_service(
            prompt_response=prompt,
            agent_name="Advice.Synthesizer",
            scope="simula.advice.synth_t2",
            timeout=45,
        )
        doc = self._parse_advice_json(resp.json or resp.text)
        if not doc:
            log.warning("[Advice] synth_t2 returned invalid JSON")
            return None

        vec = await _embed_doc(self._flatten_advice(doc))
        rows = await cypher_query(
            """
            WITH $doc AS d, $vec AS emb
            CREATE (a:Advice {
              id: randomUUID(),
              level: 2,
              kind: 'code_advice',
              text: d.text,
              checklist: d.checklist,
              donts: d.donts,
              validation: d.validation,
              scope: d.scope,
              weight: 2.0,
              sim_threshold: $thr,
              occurrences: size(d.source_ids),
              last_seen: timestamp(),
              impact: 0.0,
              embedding: emb
            })
            WITH a, d
            UNWIND d.source_ids AS sid
            MATCH (s:Advice {id:sid})
            MERGE (s)-[:MERGED_INTO]->(a)
            RETURN a.id AS id
            """,
            {"doc": doc, "vec": vec, "thr": SIM_T2_MERGE},
        )
        if not rows:
            log.warning("[Advice] synth_t2 create returned no rows")
            return None
        return rows[0]["id"]

    async def _fetch_t1_payloads(self, ids: list[str]) -> list[dict[str, Any]]:
        return (
            await cypher_query(
                """
            MATCH (a:Advice) WHERE a.id IN $ids
            OPTIONAL MATCH (a)-[:DERIVED_FROM]->(ev:ErrorEvent)
            RETURN a.id AS id, a.text AS text, ev.file AS file, ev.symbol AS symbol, ev.diff AS diff
            """,
                {"ids": ids},
            )
            or []
        )

    # -------------------------------------------------------------- T3 SYNTHESIS

    async def merge_t2_to_t3(self, t2_id: str) -> str | None:
        """
        Merge several similar T2 Advice docs into a cross-module T3 Advice doc
        using the prompt spec scope `simula.advice.synth_t3`.
        """
        rows = await cypher_query(
            """
            MATCH (a:Advice {id:$id, level:2})
            CALL db.index.vector.queryNodes('advice_embedding_idx', 12, a.embedding) YIELD node, score
            WHERE node.level = 2 AND node.id <> a.id AND score >= $thr
            RETURN node.id AS id, score
            ORDER BY score DESC
            """,
            {"id": t2_id, "thr": SIM_T2_MERGE},
        )
        peer_ids = [t2_id] + [r["id"] for r in (rows or [])]
        if len(peer_ids) < PROMOTE_MIN_T2:
            return None

        t2_docs = await self._fetch_t2_docs(peer_ids)
        prompt = await build_prompt(
            scope="simula.advice.synth_t3",
            context={"advice_docs": t2_docs},
            summary="Create cross-module architectural guidance (strict JSON).",
        )
        resp = await call_llm_service(
            prompt_response=prompt,
            agent_name="Advice.Synthesizer",
            scope="simula.advice.synth_t3",
            timeout=60,
        )
        doc = self._parse_advice_json(resp.json or resp.text)
        if not doc:
            log.warning("[Advice] synth_t3 returned invalid JSON")
            return None

        vec = await _embed_doc(self._flatten_advice(doc))
        rows2 = await cypher_query(
            """
            WITH $doc AS d, $vec AS emb
            CREATE (a:Advice {
              id: randomUUID(),
              level: 3,
              kind: 'code_advice',
              text: d.text,
              checklist: d.checklist,
              donts: d.donts,
              validation: d.validation,
              scope: d.scope,
              weight: 3.0,
              sim_threshold: 0.75,
              occurrences: size(d.source_ids),
              last_seen: timestamp(),
              impact: 0.0,
              embedding: emb
            })
            WITH a, d
            UNWIND d.source_ids AS sid
            MATCH (s:Advice {id:sid})
            MERGE (s)-[:MERGED_INTO]->(a)
            RETURN a.id AS id
            """,
            {"doc": doc, "vec": vec},
        )
        if not rows2:
            log.warning("[Advice] merge_t2_to_t3 create returned no rows")
            return None
        return rows2[0]["id"]

    async def _fetch_t2_docs(self, ids: list[str]) -> list[dict[str, Any]]:
        return (
            await cypher_query(
                """
            MATCH (a:Advice) WHERE a.id IN $ids
            RETURN a.id AS id, a.text AS text, a.checklist AS checklist, a.donts AS donts,
                   a.validation AS validation, a.scope AS scope
            """,
                {"ids": ids},
            )
            or []
        )

    # ----------------------------------------------------------- RETRIEVAL/INJECT

    async def retrieve_for(
        self,
        *,
        goal: str,
        target_fqname: str | None,
        local_context: str | None,
        k: int = TOPK_INJECT,
        extra_queries: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Programmatic retrieval (used by callers that don't go through the lens).
        For prompt-time retrieval, prefer the semantic lenses.

        Supports multi-query composition via `extra_queries` (mean-pooled).
        """
        q_parts: list[str] = [
            goal or "",
            f"Target:{target_fqname or ''}",
            f"Context:\n{local_context or ''}",
        ]
        if extra_queries:
            q_parts.extend([q for q in extra_queries if q])

        qvec = await _embed_query(q_parts)

        rows = (
            await cypher_query(
                """
            CALL db.index.vector.queryNodes('advice_embedding_idx', $limit, $qvec) YIELD node, score
            WHERE node.level >= 1
            RETURN node.id AS id, node.level AS level, node.text AS text,
                   node.checklist AS checklist, node.donts AS donts, node.validation AS validation,
                   node.scope AS scope, node.weight AS weight, node.sim_threshold AS thr,
                   node.last_seen AS last_seen, score
            ORDER BY score DESC
            """,
                {"qvec": qvec, "limit": k * 4},
            )
            or []
        )

        def prox(scope: list[str]) -> float:
            if not scope:
                return 1.0
            tf = target_fqname or ""
            s = " ".join(scope)
            if tf and tf in s:
                return 1.2
            if tf and tf.split("::")[0] in s:
                return 1.1
            return 1.0

        def recency(last_seen_ms: int | None) -> float:
            try:
                if not last_seen_ms:
                    return 1.0
                days = max(
                    0.0,
                    (time.time() * 1000.0 - float(last_seen_ms)) / (1000.0 * 60 * 60 * 24),
                )
                return 1.0 + min(0.2, 0.02 * (1.0 / (1.0 + days)))
            except Exception:
                return 1.0

        ranked = sorted(
            rows,
            key=lambda r: float(r.get("score", 0.0))
            * float(r.get("weight", 1.0))
            * prox(r.get("scope") or [])
            * recency(r.get("last_seen")),
            reverse=True,
        )
        return ranked[:k]

    async def retrieve_for_context(
        self,
        ctx: dict[str, Any],
        k: int = TOPK_INJECT,
    ) -> dict[str, Any]:
        """
        Convenience for orchestrators/lenses: takes an SCL/Planner context.
        """
        goal = (ctx.get("goal") or "").strip()
        target = ctx.get("target_fqname")
        local = ctx.get("history_summary") or ctx.get("context_summary") or ""
        # Optional: allow callers to pass query hints: ctx["advice_query_hints"] = ["AST", "pytest -k ..."]
        hints = ctx.get("advice_query_hints") if isinstance(ctx, dict) else None
        items = await self.retrieve_for(
            goal=goal,
            target_fqname=target,
            local_context=local,
            k=k,
            extra_queries=hints,
        )
        return {
            "advice_items": items,
            "advice_meta": {"ids": [i["id"] for i in items], "selected": len(items)},
        }

    # ------------------------------------------------------------- FEEDBACK LOOP

    async def record_injection(self, advice_ids: list[str], episode_id: str) -> None:
        """Persist that specific advices were injected for an episode/run."""
        if not advice_ids or not episode_id:
            return
        await cypher_query(
            """
            MATCH (a:Advice) WHERE a.id IN $ids
            MERGE (e:Episode {id:$ep})
              ON CREATE SET e.at = timestamp()
            MERGE (a)-[:APPLIED_IN {at: timestamp(), prevented: NULL}]->(e)
            """,
            {"ids": advice_ids, "ep": episode_id},
        )

    async def mark_prevented(self, advice_ids: list[str], episode_id: str, prevented: bool) -> None:
        """Mark whether an injected advice likely prevented a reoccurrence in this episode."""
        if not advice_ids or not episode_id:
            return
        await cypher_query(
            """
            MATCH (a:Advice)-[r:APPLIED_IN]->(e:Episode {id:$ep})
            WHERE a.id IN $ids
            SET r.prevented = $prevented
            """,
            {"ids": advice_ids, "ep": episode_id, "prevented": bool(prevented)},
        )

    async def reward(self, advice_ids: list[str], bonus: float = 0.25):
        """Positive update: advice helped; increase weight, bump impact and recency."""
        if not advice_ids:
            return
        await cypher_query(
            """
            MATCH (a:Advice) WHERE a.id IN $ids
            SET a.weight = a.weight + $bonus,
                a.last_seen = timestamp(),
                a.occurrences = coalesce(a.occurrences,0)+1,
                a.impact = coalesce(a.impact,0.0) + 0.02
            """,
            {"ids": advice_ids, "bonus": bonus},
        )

    async def punish(self, advice_ids: list[str], malus: float = 0.15):
        """Negative update: advice was misleading/noisy; reduce weight and impact."""
        if not advice_ids:
            return
        await cypher_query(
            """
            MATCH (a:Advice) WHERE a.id IN $ids
            SET a.weight =
                  CASE WHEN a.weight - $malus < 0.1 THEN 0.1 ELSE a.weight - $malus END,
                a.impact =
                  CASE WHEN coalesce(a.impact,0.0) - 0.01 < 0.0 THEN 0.0 ELSE a.impact - 0.01 END
            """,
            {"ids": advice_ids, "malus": malus},
        )

    async def decay(self):
        """Time-based decay so stale advice naturally loses influence."""
        await cypher_query(
            """
            MATCH (a:Advice)
            WITH a,
                duration({milliseconds: timestamp() - coalesce(a.last_seen, timestamp())}).days AS days
            // 0.5^x = exp(x * log(0.5))
            SET a.weight = coalesce(a.weight, 1.0) *
                        exp( toFloat(days) / toFloat($hl) * log(0.5) )
            """,
            {"hl": HALF_LIFE_DAYS},
        )

    # ------------------------------------------------------------------- UTILITIES

    def _parse_advice_json(self, text_or_obj: Any) -> dict[str, Any] | None:
        """
        Tolerant JSON parser: accepts dict, list[0], or JSON-string (with/without ```json fences).
        Enforces required fields and list types.
        """
        try:
            obj = text_or_obj
            if isinstance(obj, list):
                obj = obj[0] if obj else {}
            if isinstance(obj, str):
                t = obj.strip()
                if t.startswith("```"):
                    t = t.strip("`")
                    if t[:4].lower() == "json":
                        t = t[4:]
                obj = json.loads(t)
            if not isinstance(obj, dict):
                return None
            needed = {"text", "checklist", "donts", "validation", "scope", "source_ids"}
            if not needed.issubset(obj.keys()):
                return None
            for k in ("checklist", "donts", "validation", "scope", "source_ids"):
                if not isinstance(obj.get(k), list):
                    return None
            return obj
        except Exception:
            return None

    def _flatten_advice(self, d: dict[str, Any]) -> str:
        """Compact representation for re-embedding."""
        return json.dumps(
            {
                "text": d.get("text"),
                "checklist": d.get("checklist"),
                "donts": d.get("donts"),
                "validation": d.get("validation"),
                "scope": d.get("scope"),
            },
            ensure_ascii=False,
        )
