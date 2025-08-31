# systems/synapse/training/tom_trainer.py
from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np

from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)

# Tunables (safe defaults; override via env)
_TOM_MAX_VOCAB = int(os.getenv("TOM_MAX_VOCAB", "5000"))
_TOM_ALPHA = float(os.getenv("TOM_SMOOTHING_ALPHA", "0.5"))
_TOM_MIN_TRANSCRIPTS = int(os.getenv("TOM_MIN_TRANSCRIPTS", "10"))
_TOM_MIN_SAMPLES_PER_ROLE = int(os.getenv("TOM_MIN_SAMPLES_PER_ROLE", "25"))
_TOM_TOPK_NEXT = int(os.getenv("TOM_TOPK_NEXT", "5"))
_TOM_MAX_PREV_FOR_TOPK = int(os.getenv("TOM_MAX_PREV_FOR_TOPK", "1500"))  # limit payload size

_BOS = "<bos>"
_EOS = "<eos>"
_UNK = "<unk>"

_token_re = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]", re.UNICODE)


def _tok(s: str) -> list[str]:
    if not isinstance(s, str):
        s = str(s)
    return [t.lower() for t in _token_re.findall(s)]


def _build_sequences(samples: list[str]) -> list[list[str]]:
    seqs: list[list[str]] = []
    for s in samples:
        toks = _tok(s)
        if not toks:
            continue
        seqs.append([_BOS] + toks + [_EOS])
    return seqs


def _build_vocab(seqs: list[list[str]], max_vocab: int) -> tuple[dict[str, int], list[str]]:
    cnt = Counter()
    for seq in seqs:
        cnt.update(seq)
    # Always include special tokens
    most_common = [w for w, _ in cnt.most_common(max(0, max_vocab - 3))]
    vocab = [_UNK, _BOS, _EOS] + [w for w in most_common if w not in {_UNK, _BOS, _EOS}]
    stoi = {w: i for i, w in enumerate(vocab)}
    return stoi, vocab


def _id_or_unk(stoi: dict[str, int], w: str) -> int:
    return stoi.get(w, stoi[_UNK])


def _unigram_bigram_counts(
    seqs: list[list[str]],
    stoi: dict[str, int],
) -> tuple[np.ndarray, np.ndarray]:
    V = len(stoi)
    uni = np.zeros((V,), dtype=np.float64)
    bi = np.zeros((V, V), dtype=np.float64)
    for seq in seqs:
        ids = [_id_or_unk(stoi, w) for w in seq]
        for i, wid in enumerate(ids):
            uni[wid] += 1.0
            if i > 0:
                bi[ids[i - 1], wid] += 1.0
    return uni, bi


def _perplexity(seqs: list[list[str]], uni: np.ndarray, bi: np.ndarray, alpha: float) -> float:
    """
    Bigram model with Laplace smoothing:
      p(w_t | w_{t-1}) = (C(w_{t-1},w_t) + alpha) / (C(w_{t-1}) + alpha * V)
    """
    V = bi.shape[0]
    uni + alpha * V  # (V,)
    for seq in seqs:
        [
            _id_or_unk({w: i for i, w in enumerate(range(V))}, 0),
        ]  # dummy to keep type hints happy
        # Proper id mapping:
        # We'll re-map explicitly for speed/clarity outside: convert once per role before call.
        pass  # will be replaced at call site
    # NOTE: Above scaffolding replaced with role-aware function; see _evaluate_role below.
    return float("inf")  # placeholder; not used directly


def _evaluate_role(
    seqs: list[list[str]],
    stoi: dict[str, int],
    uni: np.ndarray,
    bi: np.ndarray,
    alpha: float,
) -> float:
    V = bi.shape[0]
    logp_sum = 0.0
    n_tokens = 0
    denom = uni + alpha * V  # (V,)
    for seq in seqs:
        ids = [_id_or_unk(stoi, w) for w in seq]
        for i in range(1, len(ids)):
            prev_id, cur_id = ids[i - 1], ids[i]
            num = bi[prev_id, cur_id] + alpha
            p = num / (denom[prev_id] if denom[prev_id] > 0 else alpha * V)
            if p <= 0:
                continue
            logp_sum += np.log(p)
            n_tokens += 1
    if n_tokens == 0:
        return float("inf")
    avg_logp = logp_sum / n_tokens
    return float(np.exp(-avg_logp))  # perplexity


def _topk_table(
    stoi: dict[str, int],
    itos: list[str],
    uni: np.ndarray,
    bi: np.ndarray,
    alpha: float,
) -> list[dict[str, Any]]:
    """
    Build a compact table of next-token recommendations for the most common prev tokens.
    Only include up to _TOM_MAX_PREV_FOR_TOPK prev tokens (by unigram count).
    """
    V = bi.shape[0]
    order = np.argsort(-uni)  # descending by frequency
    order = [int(i) for i in order if uni[int(i)] > 0][:_TOM_MAX_PREV_FOR_TOPK]
    table: list[dict[str, Any]] = []
    for prev_id in order:
        denom = uni[prev_id] + alpha * V
        probs = (bi[prev_id, :] + alpha) / (denom if denom > 0 else alpha * V)
        # top-k next excluding BOS (rarely meaningful as a next token)
        topk_ids = list(np.argsort(-probs))[: _TOM_TOPK_NEXT + 2]
        filtered = [int(t) for t in topk_ids if itos[int(t)] != _BOS][:_TOM_TOPK_NEXT]
        table.append(
            {
                "prev": itos[prev_id],
                "next": [[itos[nid], float(probs[nid])] for nid in filtered],
            },
        )
    return table


async def _persist_role_model(
    role: str,
    vocab: list[str],
    unigram_counts: list[float],
    topk_table_payload: list[dict[str, Any]],
    alpha: float,
    metrics: dict[str, float],
) -> None:
    """
    Versioned upsert for a single role's ToM model into Neo4j.
    """
    await cypher_query(
        """
        MATCH (m:UnityToMModel {role:$role})
        WITH coalesce(max(m.version), 0) AS v
        CREATE (new:UnityToMModel {
            role: $role,
            version: v + 1,
            created_at: datetime(),
            alpha: $alpha,
            vocab: $vocab,
            unigram_counts: $unigram,
            topk: $topk,
            metrics: $metrics
        })
        """,
        {
            "role": role,
            "alpha": float(alpha),
            "vocab": list(vocab),
            "unigram": [float(x) for x in unigram_counts],
            "topk": topk_table_payload,
            "metrics": {k: float(v) for k, v in metrics.items()},
        },
    )


class TheoryOfMindTrainer:
    """
    Fine-tunes generative models, one for each participant role, to predict
    arguments based on the history of deliberations.
    """

    _instance: TheoryOfMindTrainer | None = None
    _lock: asyncio.Lock

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def _fetch_training_data(self, limit: int = 200) -> list[dict[str, Any]]:
        """
        Fetch full deliberation transcripts from the graph.
        """
        query = """
        MATCH (d:Deliberation)-[:HAS_TRANSCRIPT]->(tc:TranscriptChunk)
        WITH d, tc ORDER BY tc.turn ASC
        WITH d.id AS deliberation_id, collect({role: tc.role, content: tc.content}) AS transcript
        RETURN deliberation_id, transcript
        LIMIT $limit
        """
        rows = await cypher_query(query, {"limit": limit}) or []
        return rows if isinstance(rows, list) else []

    def _create_training_samples(self, transcripts: list[dict[str, Any]]) -> dict[str, list[str]]:
        """
        Processes raw transcripts into structured training data per-role.
        Output: { "SafetyCritic": ["<prompt>response", ...], ... }
        """
        samples_by_role: dict[str, list[str]] = defaultdict(list)
        for deliberation in transcripts:
            transcript = deliberation.get("transcript") or []
            if not isinstance(transcript, list) or len(transcript) < 2:
                continue
            for i in range(1, len(transcript)):
                history = transcript[:i]
                current = transcript[i]
                role = str(current.get("role") or "").strip()
                content = str(current.get("content") or "")
                if not role or not content:
                    continue

                # Keep prompt style for continuity with your original dataset shape
                prompt = [
                    "The following is a deliberation transcript. Based on your role, provide the next response.",
                    "",
                ]
                for turn in history:
                    prompt.append(
                        f"{turn.get('role', 'Unknown')}: {turn.get('content', '').strip()}",
                    )
                prompt.append(f"{role}: ")
                prefix = "\n".join(prompt)
                samples_by_role[role].append(prefix + content)
        return samples_by_role

    async def train_cycle(self):
        """
        Runs a full training cycle for the Theory of Mind models:
          - Fetch transcripts
          - Build per-role samples
          - Train role-conditioned bigram LMs with Laplace smoothing
          - Evaluate perplexity
          - Persist versioned artifacts to Neo4j
        """
        if self._lock.locked():
            logger.info("[ToMTrainer] Training already in progress; skipping.")
            return

        async with self._lock:
            logger.info("[ToMTrainer] Starting training cycle for Unity's ToM models.")
            transcripts = await self._fetch_training_data()

            if len(transcripts) < _TOM_MIN_TRANSCRIPTS:
                logger.info(
                    "[ToMTrainer] Insufficient deliberation data (%d transcripts). Skipping.",
                    len(transcripts),
                )
                return

            samples_by_role = self._create_training_samples(transcripts)
            trained_any = False

            for role, samples in samples_by_role.items():
                if len(samples) < _TOM_MIN_SAMPLES_PER_ROLE:
                    logger.info(
                        "[ToMTrainer] Role '%s' has too few samples (%d). Skipping.",
                        role,
                        len(samples),
                    )
                    continue

                # Build sequences and split
                seqs = _build_sequences(samples)
                if not seqs:
                    continue
                n = len(seqs)
                idx = np.arange(n)
                rng = np.random.default_rng(2025)
                rng.shuffle(idx)
                split = max(1, int(0.85 * n))
                train_ids, val_ids = idx[:split], idx[split:]
                train_seqs = [seqs[i] for i in train_ids]
                val_seqs = [seqs[i] for i in val_ids] if len(val_ids) > 0 else train_seqs[:]

                # Vocab & counts
                stoi, vocab = _build_vocab(train_seqs, _TOM_MAX_VOCAB)
                # Ensure specials exist
                for sp in (_UNK, _BOS, _EOS):
                    if sp not in stoi:
                        idx_sp = len(stoi)
                        stoi[sp] = idx_sp
                        vocab.append(sp)

                uni, bi = _unigram_bigram_counts(train_seqs, stoi)

                # Evaluate perplexity on validation set
                ppl = _evaluate_role(val_seqs, stoi, uni, bi, _TOM_ALPHA)

                # Assemble compact top-k table
                topk_tbl = _topk_table(stoi, vocab, uni, bi, _TOM_ALPHA)

                metrics = {
                    "perplexity": float(ppl),
                    "n_train_seqs": float(len(train_seqs)),
                    "n_val_seqs": float(len(val_seqs)),
                    "vocab_size": float(len(vocab)),
                }

                await _persist_role_model(
                    role=role,
                    vocab=vocab,
                    unigram_counts=uni.tolist(),
                    topk_table_payload=topk_tbl,
                    alpha=_TOM_ALPHA,
                    metrics=metrics,
                )

                logger.info(
                    "[ToMTrainer] Role '%s' updated: vocab=%d train=%d val=%d ppl=%.2f",
                    role,
                    len(vocab),
                    len(train_seqs),
                    len(val_seqs),
                    ppl,
                )
                trained_any = True

            if not trained_any:
                logger.info(
                    "[ToMTrainer] No roles met minimum sample thresholds; nothing to update.",
                )
            else:
                logger.info("[ToMTrainer] Training complete. All eligible ToM models updated.")


# Singleton export
tom_trainer = TheoryOfMindTrainer()
