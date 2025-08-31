# systems/atune/salience/heads.py

import re
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from systems.atune.processing.canonical import CanonicalEvent


class SalienceScore(BaseModel):
    """A standardized container for the output of a salience head."""

    head_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    details: dict = Field(default_factory=dict)


class SalienceHead(ABC):
    """Abstract base class for all salience-scoring modules."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique, kebab-case name of the head."""
        pass

    @abstractmethod
    async def score(self, event: CanonicalEvent) -> SalienceScore:
        """
        Computes the salience score for a given canonical event.
        """
        pass


# --- Concrete Implementations ---


class NoveltyHead(SalienceHead):
    """Scores events based on whether their content has been seen before."""

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
    """Scores events based on the presence of high-value keywords."""

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
    """Scores events for explicit risks using compiled regex patterns."""

    def __init__(self, threat_patterns: dict[str, str]):
        self.threat_patterns = {
            name: re.compile(pattern, re.IGNORECASE) for name, pattern in threat_patterns.items()
        }

    @property
    def name(self) -> str:
        return "risk-head"

    async def score(self, event: CanonicalEvent) -> SalienceScore:
        """Scans for high-risk patterns in the event content."""
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
