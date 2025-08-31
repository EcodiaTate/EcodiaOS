# systems/atune/safety/reflex_catalog.py
from __future__ import annotations

from typing import Any

# Map from RiskHead detail key → reflex action
# action ∈ {"block","redact","quarantine","throttle"}
REFLEX_RULES: dict[str, dict[str, Any]] = {
    "PII_SSN": {
        "action": "redact",
        "fields": ["params.query", "body.text"],
        "reason": "PII detected",
    },
    "CONFIDENTIAL_MARKER": {"action": "block", "fields": [], "reason": "Confidential content"},
    "MALWARE_INDICATOR": {"action": "quarantine", "fields": [], "reason": "Potential malware"},
    "RATE_SPIKE": {"action": "throttle", "fields": [], "reason": "Abnormal rate"},
}


def decide(risk_details: dict[str, Any]) -> dict[str, Any] | None:
    for key, rule in REFLEX_RULES.items():
        if risk_details.get(key):
            return dict(rule, matched=key)
    return None


def apply_redactions(payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """
    Redacts dotted paths in a nested dict. Non-throwing: missing paths are ignored.
    """
    redacted = {**payload}
    for path in fields:
        parts = path.split(".")
        cur = redacted
        for i, p in enumerate(parts):
            if isinstance(cur, dict) and p in cur:
                if i == len(parts) - 1:
                    cur[p] = "[REDACTED]"
                else:
                    cur = cur[p]
            else:
                break
    return redacted
