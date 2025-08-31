# systems/unity/core/policy/safety_policy.py
from __future__ import annotations

import re
from typing import Any

from core.utils.neo.cypher_query import cypher_query

# Simple in-process cache; call clear_rules_cache() after you edit rules in Neo4j
_rules_cache: list[dict] | None = None


async def _load_rules_from_db() -> list[dict]:
    try:
        rows = await cypher_query(
            "MATCH (r:ConstitutionRule {active:true}) RETURN r.id AS id, r.pattern AS pattern",
            {},
        )
        return rows or []
    except Exception:
        return []


async def get_rules() -> list[dict]:
    global _rules_cache
    if _rules_cache is None:
        _rules_cache = await _load_rules_from_db()
    return _rules_cache


def clear_rules_cache() -> None:
    global _rules_cache
    _rules_cache = None


def _coerce_text(val: Any) -> str:
    if isinstance(val, str):
        return val
    try:
        return str(val)
    except Exception:
        return ""


def _text_from_spec(spec: Any) -> str:
    topic = getattr(spec, "topic", "") or ""
    inputs = getattr(spec, "inputs", []) or []
    parts: list[str] = [topic]
    for i in inputs:
        # Pydantic model or plain dict
        v = getattr(i, "value", None)
        if v is None and isinstance(i, dict):
            v = i.get("value")
        if v:
            parts.append(_coerce_text(v))
    return " ".join(parts).strip()


async def violates(spec: Any) -> tuple[bool, str | None, str | None]:
    """
    Return (violates, rule_id, excerpt).
    Fully async. No run_until_complete. Tolerates empty/malformed rules.
    """
    text = _text_from_spec(spec)
    if not text:
        return False, None, None

    rules = await get_rules()
    if not rules:
        # No active rules → allow
        return False, None, None

    for r in rules:
        pat = (r.get("pattern") or "").strip()
        if not pat:
            continue
        try:
            if re.search(pat, text, flags=re.I | re.S):
                return True, r.get("id"), text[:280]
        except re.error:
            # Skip bad regex patterns
            continue
    return False, None, None
