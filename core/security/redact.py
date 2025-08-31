# core/security/redact.py
from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r'(?:api|secret|token|key)\s*[:=]\s*["\']?([A-Za-z0-9_\-]{16,})', re.I),
    re.compile(r"Bearer\s+([A-Za-z0-9._\-]{10,})", re.I),
    re.compile(r"(?:(sk|rk|pk|ak)_[A-Za-z0-9]{16,})"),
]


def redact(text: str, replacement: str = "*****") -> str:
    """Redact common secret/token patterns from logs or LLM-visible text."""
    out = text
    for p in _SECRET_PATTERNS:
        out = p.sub(replacement, out)
    return out
