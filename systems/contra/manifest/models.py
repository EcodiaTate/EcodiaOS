from __future__ import annotations

from typing import Literal

try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    from pydantic.v1 import BaseModel  # type: ignore


class Assertion(BaseModel):
    id: str
    kind: Literal[
        "alias_parity",
        "header_discipline",
        "tool_required_args",
        "pydantic_drift",
        "illegal_self_edge",
    ]
    severity: Literal["P0", "P1", "P2"] = "P1"
    auto_fix: bool = False


class Diagnostic(BaseModel):
    assertion_id: str
    status: Literal["pass", "fail", "warn"]
    evidence: list[dict] = []
    suggested_fixes: list[dict] = []
    confidence: float = 1.0
    pairs: list[dict] = []  # [{"left": "...", "right": "...", "reason": "..."}]
