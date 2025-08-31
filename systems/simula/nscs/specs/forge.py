from __future__ import annotations

from .dsl import APISignature, ModuleSpec, SystemSpec


def natural_language_to_spec(nl: str, *, name: str = "system") -> SystemSpec:
    # Seed spec; wire your LLM+Qora expansion later.
    mod = ModuleSpec(path="app/core.py", apis=[APISignature(name="main", params={}, returns="int")])
    return SystemSpec(name=name, modules=[mod])
