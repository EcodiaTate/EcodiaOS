# systems/axon/safety/reflex.py

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from systems.axon.schemas import AxonIntent


class ReflexVerdict(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"


@dataclass
class ReflexResult:
    action: ReflexVerdict
    reason: str = ""
    redactions: dict[str, Any] = None


class ReflexEngine:
    """
    Zero-LLM reflexes that run before twin/conformal/live.
    Keep it deterministic and fast.
    """

    _pii_regex = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")  # example US SSN

    def evaluate(self, intent: AxonIntent) -> ReflexResult:
        # Example: redact queries containing obvious PII
        params_str = str(intent.params or "")
        if self._pii_regex.search(params_str):
            redacted = dict(intent.params or {})
            redacted_str = self._pii_regex.sub("[REDACTED_SSN]", str(redacted))
            return ReflexResult(
                action=ReflexVerdict.REDACT,
                reason="PII detected in params",
                redactions={"params": redacted_str},
            )
        # Block unsupported high-risk capabilities without rollback
        if intent.risk_tier == "high" and not intent.rollback_contract:
            return ReflexResult(
                ReflexVerdict.BLOCK,
                reason="High-risk intent missing rollback contract",
            )
        return ReflexResult(ReflexVerdict.ALLOW)
