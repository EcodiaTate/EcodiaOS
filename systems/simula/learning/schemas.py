from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ErrorEventIngest(BaseModel):
    episode_id: str
    turn_id: str
    file: str
    symbol: str | None = None
    diff: str = ""
    message: str
    tags: list[str] = Field(default_factory=list)
    context_snippet: str | None = None
    tool: str | None = None


class AdviceDoc(BaseModel):
    id: str
    level: int
    kind: str = "code_advice"
    text: str
    checklist: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)
    weight: float = 1.0
    sim_threshold: float = 0.84
    occurrences: int = 1
    last_seen: int = 0
    impact: float = 0.0
    conflicts: list[str] = Field(default_factory=list)


class RetrieveResult(BaseModel):
    id: str
    level: int
    text: str
    checklist: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)
    weight: float
    thr: float
    score: float
