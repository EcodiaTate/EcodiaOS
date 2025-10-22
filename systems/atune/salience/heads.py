# systems/atune/salience/heads.py
import asyncio
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

from core.llm.embeddings_gemini import get_embedding
from systems.atune.processing.canonical import CanonicalEvent
from systems.equor.core.identity.registry import IdentityRegistry, RegistryError


class SalienceScore(BaseModel):
    head_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    details: dict = Field(default_factory=dict)


class SalienceHead(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    async def score(self, event: CanonicalEvent) -> SalienceScore: ...


# ---------------- Concrete Heads ----------------


class NoveltyHead(SalienceHead):
    def __init__(self):
        self._seen_hashes: set[str] = set()

    @property
    def name(self) -> str:
        return "novelty-head"

    async def score(self, event: CanonicalEvent) -> SalienceScore:
        is_novel = event.text_hash not in self._seen_hashes
        if is_novel:
            self._seen_hashes.add(event.text_hash)
            score = 1.0
        else:
            score = 0.0
        return SalienceScore(
            head_name=self.name,
            score=score,
            details={"text_hash": event.text_hash, "is_novel": is_novel},
        )


class KeywordHead(SalienceHead):
    def __init__(self, critical_keywords: list[str]):
        self._critical_keywords = {kw.lower() for kw in critical_keywords}

    @property
    def name(self) -> str:
        return "keyword-head"

    async def score(self, event: CanonicalEvent) -> SalienceScore:
        found_keywords = set()
        content = " ".join(event.text_blocks).lower()
        for keyword in self._critical_keywords:
            if keyword in content:
                found_keywords.add(keyword)
        score = 1.0 if found_keywords else 0.0
        return SalienceScore(
            head_name=self.name,
            score=score,
            details={"found_keywords": list(found_keywords)},
        )


class RiskHead(SalienceHead):
    def __init__(self, threat_patterns: dict[str, str]):
        self.threat_patterns = {
            name: re.compile(pattern, re.IGNORECASE) for name, pattern in threat_patterns.items()
        }

    @property
    def name(self) -> str:
        return "risk-head"

    async def score(self, event: CanonicalEvent) -> SalienceScore:
        matched_patterns = set()
        content = " ".join(event.text_blocks)
        for name, compiled_regex in self.threat_patterns.items():
            if compiled_regex.search(content):
                matched_patterns.add(name)
        score = 1.0 if matched_patterns else 0.0
        return SalienceScore(
            head_name=self.name,
            score=score,
            details={
                "matched_patterns": list(matched_patterns),
                "reflex_trigger": bool(matched_patterns),
            },
        )


# ---------------- Identity Relevance ----------------


class IdentityRelevanceHead(SalienceHead):
    """
    Scores event salience based on semantic similarity to the system's
    core identity Facets (Equor).
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        self.registry = IdentityRegistry()
        self._cache_ttl = cache_ttl_seconds
        self._last_fetch_time: float = 0.0
        self._facet_cache: list[dict[str, Any]] = []
        self._facet_embeddings: np.ndarray | None = None
        self._lock = asyncio.Lock()
        # Configurable agent/profile (defaults mirror your deployment)
        self._agent = os.getenv("IDENTITY_AGENT", "EcodiaOS.System")
        self._profile = os.getenv("IDENTITY_PROFILE", "ecodia")

    @property
    def name(self) -> str:
        return "identity-relevance-head"

    async def _refresh_cache(self) -> None:
        try:
            profile, facets, _rules = await self.registry.get_active_components_for_profile(
                agent=self._agent,
                profile_name=self._profile,
            )
        except RegistryError as e:
            # Don’t spam logs on every event; only warn on refresh attempts.
            print(
                f"WARNING: IdentityRelevanceHead: profile not found "
                f"(agent='{self._agent}', profile='{self._profile}'): {e}",
            )
            self._facet_cache = []
            self._facet_embeddings = None
            return
        except Exception as e:
            print(f"ERROR: IdentityRelevanceHead: unexpected error fetching profile: {e}")
            self._facet_cache = []
            self._facet_embeddings = None
            return

        self._facet_cache = facets or []
        if not self._facet_cache:
            # Nothing to embed – leave embeddings as None (score -> 0.0)
            self._facet_embeddings = None
            return

        # Pull texts to embed; tolerate different shapes (properties/text/name)
        facet_texts: list[str] = []
        for f in self._facet_cache:
            # tolerate nested property shapes; prefer .text if present
            text = (
                (f.get("text"))
                or ((f.get("properties") or {}).get("text"))
                or (f.get("name"))
                or ""
            )
            facet_texts.append(text)

        # Embed all facets (best effort)
        try:
            embs = await asyncio.gather(
                *[get_embedding(t, task_type="RETRIEVAL_DOCUMENT") for t in facet_texts],
            )
            valid = [e for e in embs if e is not None]
            self._facet_embeddings = np.array(valid, dtype=np.float32) if valid else None
        except Exception as e:
            print(f"ERROR: IdentityRelevanceHead: embedding facets failed: {e}")
            self._facet_embeddings = None

    async def _get_identity_facets(self) -> np.ndarray | None:
        now = time.time()
        if now - self._last_fetch_time > self._cache_ttl:
            async with self._lock:
                # double-check under lock
                if now - self._last_fetch_time > self._cache_ttl:
                    await self._refresh_cache()
                    self._last_fetch_time = now
        return self._facet_embeddings

    async def score(self, event: CanonicalEvent) -> SalienceScore:
        facet_embeddings = await self._get_identity_facets()

        if facet_embeddings is None or not event.text_blocks:
            return SalienceScore(
                head_name=self.name,
                score=0.0,
                details={
                    "reason": "no_facets_or_no_event_text",
                    "agent": self._agent,
                    "profile": self._profile,
                    "facets_cached": len(self._facet_cache),
                },
            )

        event_text = " ".join(event.text_blocks)
        try:
            event_embedding_list = await get_embedding(event_text, task_type="RETRIEVAL_QUERY")
        except Exception as e:
            return SalienceScore(
                head_name=self.name,
                score=0.0,
                details={"error": f"embed_failed: {e}"},
            )

        if not event_embedding_list:
            return SalienceScore(
                head_name=self.name,
                score=0.0,
                details={"error": "empty_event_embedding"},
            )

        event_embedding = np.array(event_embedding_list, dtype=np.float32)

        # Normalize (cosine similarity)
        denom_event = np.linalg.norm(event_embedding)
        denom_facets = np.linalg.norm(facet_embeddings, axis=1)
        if denom_event == 0.0 or np.any(denom_facets == 0.0):
            return SalienceScore(
                head_name=self.name,
                score=0.0,
                details={"error": "zero_norm_embeddings"},
            )

        norm_event = event_embedding / denom_event
        norm_facets = facet_embeddings / denom_facets[:, np.newaxis]
        sims = np.dot(norm_facets, norm_event)

        best_idx = int(np.argmax(sims))
        max_sim = float(sims[best_idx])
        best_facet = self._facet_cache[best_idx] if 0 <= best_idx < len(self._facet_cache) else {}

        # Common id shapes
        best_id = best_facet.get("id") or (best_facet.get("properties") or {}).get("id") or None
        best_name = (
            best_facet.get("name") or (best_facet.get("properties") or {}).get("name") or None
        )

        return SalienceScore(
            head_name=self.name,
            score=max_sim,
            details={
                "best_match_score": max_sim,
                "best_match_facet_id": best_id,
                "best_match_facet_name": best_name,
                "facet_count": len(self._facet_cache),
            },
        )
