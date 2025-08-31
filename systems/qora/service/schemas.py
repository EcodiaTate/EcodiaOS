# systems/qora/service/schemas.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---- Dossier ----
class DossierRequest(BaseModel):
    target_fqname: str = Field(..., description="path/to/file.py or path/to/file.py::Class::func")
    intent: str = Field(..., description="What the caller is trying to do (edit/add/test/etc.)")


class DossierResponse(BaseModel):
    target_fqname: str
    intent: str
    summary: str | None = ""
    files: list[dict[str, Any]] = Field(default_factory=list)
    symbols: list[dict[str, Any]] = Field(default_factory=list)
    related: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


# ---- Subgraph ----
class SubgraphResponse(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


# ---- Blackboard ----
class BbWrite(BaseModel):
    key: str
    value: Any


class BbReadResponse(BaseModel):
    key: str
    value: Any = None


# ---- Index ----
class IndexFileRequest(BaseModel):
    path: str
