from __future__ import annotations

try:
    from pydantic import BaseModel, Field  # v1/v2 compatible usage in this file
except Exception:  # pragma: no cover
    # fallback shim if needed
    from pydantic.v1 import BaseModel, Field  # type: ignore


class ContentRef(BaseModel):
    file: str
    start: int
    end: int
    hash: str  # blake2b-hex of the referenced slice (determinism + citations)


class SystemManifest(BaseModel):
    """
    Deterministic, machine-first picture of a system/module.
    All lists/keys are produced in sorted order during build.
    """

    system: str
    commit: str = "HEAD"
    files: list[str] = Field(default_factory=list)
    imports: list[tuple[str, str]] = Field(default_factory=list)  # (from_file, imported_module)
    endpoints_used: list[dict] = Field(
        default_factory=list,
    )  # {alias, path?, method?, file, line, context?}
    tools_used: list[dict] = Field(default_factory=list)  # {uid, name, file, line, required_args?}
    models: list[dict] = Field(
        default_factory=list,
    )  # {module, class_name, fields:[{name,type,required}]}
    env: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    loops: list[dict] = Field(default_factory=list)  # {name, flag?, interval?}
    edges: dict[str, list[dict]] = Field(
        default_factory=lambda: {"imports": [], "http": [], "events": [], "tool": []},
    )
    invariants: list[str] = Field(default_factory=list)
    examples: list[dict] = Field(default_factory=list)  # canonical req/resp, tool calls, koans
    content_refs: list[ContentRef] = Field(default_factory=list)

    manifest_hash: str | None = None
    generated_at: str | None = None
