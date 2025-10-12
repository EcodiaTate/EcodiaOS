# systems/atune/schemas.py
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Mode = Literal["enrich_with_search", "escalate_to_unity", "discard"]


class AtuneDecision(BaseModel):
    mode: Mode
    reason: str | None = None
    search_query: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    tags: list[str] = []
    budget_hint: dict[str, Any] | None = None
    audit: dict[str, list[str]]

    @field_validator("reason")
    @classmethod
    def reason_required_for_escalate_discard(cls, v, info):
        if info.data.get("mode") in ("escalate_to_unity", "discard") and not v:
            raise ValueError("reason required when mode is escalate_to_unity or discard")
        return v

    @field_validator("search_query")
    @classmethod
    def query_required_for_search(cls, v, info):
        if info.data.get("mode") == "enrich_with_search" and not v:
            raise ValueError("search_query required when mode is enrich_with_search")
        return v
