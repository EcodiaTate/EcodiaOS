# systems/unity/core/t_o_m/modeler.py
from __future__ import annotations

import re
from typing import Any

from core.services.synapse import synapse
from core.utils.neo.cypher_query import cypher_query

# simple, robust tokenizer aligned with the trainer
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]", re.UNICODE)
_BOS = "<bos>"
_EOS = "<eos>"
_UNK = "<unk>"


def _tok(text: str) -> list[str]:
    if not isinstance(text, str):
        text = str(text or "")
    return [t.lower() for t in _TOKEN_RE.findall(text)] or [_UNK]


def _clean_keywords(tokens: list[tuple[str, float]], k: int = 5) -> list[str]:
    out: list[str] = []
    for w, _ in tokens:
        if w in {_BOS, _EOS, _UNK}:
            continue
        if re.fullmatch(r"\W", w):
            continue
        if any(ch.isalpha() for ch in w):  # prefer alphanumeric keywords
            out.append(w)
        if len(out) >= k:
            break
    return out


class TheoryOfMindEngine:
    """
    Singleton client that predicts likely arguments for a participant role.
    Loads the latest UnityToMModel for that role from Neo4j (trained by Synapse),
    performs bigram next-token prediction using the stored top-k table and
    unigram priors, and composes a natural-language argument.
    """

    _instance: TheoryOfMindEngine | None = None
    _cache: dict[str, dict[str, Any]]  # declare type here
    _instance: TheoryOfMindEngine | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.synapse = synapse
            cls._instance._cache = {}  # role -> model bundle
        return cls._instance

    async def _load_role_model(self, role: str) -> dict[str, Any] | None:
        """
        Pull latest UnityToMModel for role from graph and normalize into
        { 'vocab': list[str], 'stoi': dict, 'unigram': list[float], 'topk': dict[str, list[(token, p)]], 'version': int }
        """
        query = """
        MATCH (m:UnityToMModel {role:$role})
        RETURN m.vocab AS vocab, m.unigram_counts AS unigram, m.topk AS topk, m.version AS version
        ORDER BY m.version DESC
        LIMIT 1
        """
        rows = await cypher_query(query, {"role": role}) or []
        if not rows:
            return None
        row = rows[0]
        vocab = row.get("vocab") or []
        unigram = row.get("unigram") or []
        topk_rows = row.get("topk") or []

        stoi = {w: i for i, w in enumerate(vocab)}
        # Normalize topk into dict prev_token -> [(next_token, prob)...]
        topk_map: dict[str, list[tuple[str, float]]] = {}
        for entry in topk_rows:
            prev = entry.get("prev")
            next_list = entry.get("next") or []
            if isinstance(prev, str) and isinstance(next_list, list):
                # each next is [token, prob]
                cleaned: list[tuple[str, float]] = []
                for pair in next_list:
                    if isinstance(pair, list) and len(pair) == 2:
                        tkn, pr = pair[0], pair[1]
                        try:
                            cleaned.append((str(tkn), float(pr)))
                        except Exception:
                            continue
                if cleaned:
                    topk_map[prev] = cleaned

        bundle = {
            "vocab": vocab,
            "stoi": stoi,
            "unigram": unigram,
            "topk": topk_map,
            "version": int(row.get("version", 0)),
        }
        self._cache[role] = bundle
        return bundle

    async def _ensure_model(self, role: str) -> dict[str, Any] | None:
        model = self._cache.get(role)
        if model is not None:
            return model
        return await self._load_role_model(role)

    @staticmethod
    def _last_token_from_state(state: dict[str, Any]) -> str:
        # Try transcript -> last content; else current prompt/topic; else BOS
        transcript = state.get("transcript") or []
        if isinstance(transcript, list) and transcript:
            last = transcript[-1]
            content = last.get("content") if isinstance(last, dict) else str(last)
            toks = _tok(content)
            return toks[-1] if toks else _BOS
        topic = state.get("topic") or state.get("prompt") or ""
        toks = _tok(topic)
        return toks[-1] if toks else _BOS

    @staticmethod
    def _unigram_top(unigram: list[float], vocab: list[str], k: int = 5) -> list[tuple[str, float]]:
        pairs = [(vocab[i], float(c)) for i, c in enumerate(unigram) if i < len(vocab)]
        pairs.sort(key=lambda x: x[1], reverse=True)
        total = sum(c for _, c in pairs) or 1.0
        return [(w, c / total) for w, c in pairs[:k]]

    def _predict_token_topk(
        self,
        role_model: dict[str, Any],
        prev_token: str,
        k: int = 5,
    ) -> list[tuple[str, float]]:
        topk_map = role_model["topk"]
        if prev_token in topk_map:
            return topk_map[prev_token][:k]
        # fallback: try UNK
        if _UNK in topk_map:
            return topk_map[_UNK][:k]
        # final fallback: unigram
        return self._unigram_top(role_model["unigram"], role_model["vocab"], k=k)

    def _compose_argument(self, role: str, topic: str, keywords: list[str]) -> str:
        """
        Turn keyword predictions into a coherent, role-conditioned argument.
        """
        if not keywords:
            keywords = ["risks", "evidence", "impacts"]
        # Simple role-aware framing
        role_lower = role.lower()
        if "safety" in role_lower:
            lead = "From a safety perspective"
        elif "factual" in role_lower or "fact" in role_lower:
            lead = "Grounded in verifiable evidence"
        elif "proposer" in role_lower or "proponent" in role_lower:
            lead = "In support of the proposal"
        else:
            lead = f"As the {role}"

        # Use top 3 keywords for crisp focus
        focus = ", ".join(keywords[:2]) + (f", and {keywords[2]}" if len(keywords) >= 3 else "")
        topic_clause = f" regarding '{topic}'" if topic else ""
        return (
            f"{lead}{topic_clause}, I will focus on {focus}. "
            f"My position integrates prior deliberation patterns to anticipate objections and address them directly."
        )

    async def predict_argument(self, role: str, current_debate_state: dict[str, Any]) -> str:
        """
        Predict the likely argument for `role`, conditioned on the current debate state.
        Prefers Synapse-served ToM (if available) by reading the latest model
        from the graph that Synapse publishes after training.
        """
        # Load/cached model
        bundle = await self._ensure_model(role)
        topic = str(current_debate_state.get("topic") or "")
        prev_tok = self._last_token_from_state(current_debate_state)

        if bundle:
            topk = self._predict_token_topk(bundle, prev_tok, k=5)
            keywords = _clean_keywords(topk, k=5)
            return self._compose_argument(role, topic, keywords)

        # If no model exists yet, degrade gracefully using debate state
        fallback_keywords = _clean_keywords([(t, 1.0) for t in _tok(topic)], k=3)
        return self._compose_argument(role, topic, fallback_keywords)


# Singleton export
tom_engine = TheoryOfMindEngine()
