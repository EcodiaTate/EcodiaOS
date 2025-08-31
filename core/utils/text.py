# core/utils/text_helpers.py
from __future__ import annotations

import re
from typing import Any


def extract_body_from_node(
    node: dict,
    exclude=(
        "event_id",
        "confidence",
        "vector_gemini",
        "embedding",
        "timestamp",
        "user_id",
        "origin",
        "labels",
    ),
) -> str:
    return " ".join(str(v) for k, v in node.items() if k not in exclude and v is not None)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamps a number to a given range."""
    return hi if x > hi else lo if x < lo else x


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*([A-Za-z0-9_\-]{12,})"),
    re.compile(r"(?i)(bearer)\s+([A-Za-z0-9\._\-]{12,})"),
]


def redact_secrets(text: str) -> str:
    """Masks common secret-like substrings in a string."""
    s = text or ""
    for rx in _SECRET_PATTERNS:
        s = rx.sub(lambda m: f"{m.group(1)}=***REDACTED***", s)
    return s


def safe_truncate(text: str, max_chars: int = 4000) -> str:
    """Cuts a string by characters with a clean ellipsis boundary."""
    if not text or len(text) <= max_chars:
        return text or ""
    return (text[: max(0, max_chars - 1)].rstrip()) + "…"


_BAD_WORDS = {"kill", "hate", "ugly", "stupid", "idiot"}


def toxicity_hint(text: str) -> float:
    """Returns a simple 0.0 or 1.0 toxicity score based on a keyword list."""
    toks = re.findall(r"[A-Za-z]+", (text or "").lower())
    return 0.0 if (set(toks) & _BAD_WORDS) else 1.0


def baseline_metrics(
    output_text: str,
    *,
    agent: str | None = None,
    scope: str | None = None,
    facet_keys: list[str] | None = None,
    target_len: int = 220,
) -> dict[str, Any]:
    """
    Creates a lightweight, non-empty metrics scaffold for the learning loop.
    """
    return {
        "helpfulness": clamp(0.7),
        "brand_consistency": clamp(0.7),
        "toxicity": toxicity_hint(output_text),
        "agent": agent,
        "scope": scope,
        "facet_keys": list(facet_keys or []),
    }
