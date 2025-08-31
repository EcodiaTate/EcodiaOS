from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class APISignature(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    params: dict[str, str] = Field(default_factory=dict)
    returns: str = "None"


class Invariant(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    language: Literal["python", "z3", "tla"] = "python"
    body: str


class PerfBudget(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    p95_ms: int = 1000
    memory_mb: int = 512


class ModuleSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    path: str
    apis: list[APISignature] = Field(default_factory=list)
    invariants: list[Invariant] = Field(default_factory=list)
    perf: PerfBudget | None = None
    tests: list[str] = Field(default_factory=list)


class SystemSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    modules: list[ModuleSpec] = Field(default_factory=list)
    global_invariants: list[Invariant] = Field(default_factory=list)
