from __future__ import annotations

from typing import Any


def run_types_and_style(paths: list[str]) -> dict[str, Any]:
    # Real impl: run ruff + mypy in DockerSandbox; stub returns clean.
    return {"mypy": {"ok": True, "errors": 0}, "ruff": {"ok": True, "errors": 0}}
