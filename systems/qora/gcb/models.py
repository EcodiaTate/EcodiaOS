from __future__ import annotations

from typing import Literal

try:
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    from pydantic.v1 import BaseModel, Field  # type: ignore


class SnippetRef(BaseModel):
    file: str
    start: int
    end: int
    hash: str


class Koan(BaseModel):
    name: str
    kind: Literal["http", "tool", "function"]
    request: dict
    expect: dict


class GoldenContextBundle(BaseModel):
    """
    Task-scoped, deterministic context for Simula.
    Simula must refuse to generate without a valid GCB.
    """

    decision_id: str
    scope: dict  # {"system": "...", "module"?: "...", "change_kind"?: "..."}
    targets: list[dict]  # [{"file":"...", "export"?: "...", "why":"..."}]
    manifests: list[dict]  # [{"system":"...", "hash":"...", "uri"?: "..."}]
    edges_touched: dict[str, list[dict]] = Field(
        default_factory=lambda: {"imports": [], "http": [], "tool": [], "events": []},
    )
    contracts: dict[str, list[dict]] = Field(
        default_factory=lambda: {"endpoints": [], "tools": []},
    )  # endpoints: {alias,path,method,req_schema?,res_schema?}
    examples: dict[str, list[dict]] = Field(
        default_factory=lambda: {"requests": [], "tool_calls": []},
    )
    constraints: dict = Field(
        default_factory=lambda: {
            "soc_invariants": ["no_http_self_edge"],
            "security": {"equor_token_required": False},
            "budgets": {"x_budget_ms_max": 2500},
            "file_system": {"allowed_roots": ["."], "max_apply_bytes": 20000},
        },
    )
    tests: dict[str, list[Koan]] = Field(default_factory=lambda: {"acceptance": [], "koans": []})
    snippets: list[SnippetRef] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
