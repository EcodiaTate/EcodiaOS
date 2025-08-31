# file: systems/evo/__init__.py
"""
Evo package (lightweight init).

Important:
- Do NOT import engine/services/schemas here.
- Always import explicitly, e.g.:
    from systems.evo.engine import EvoEngine
    from systems.evo.schemas import ConflictNode

Rationale:
- Avoid package-level side effects that can trigger circular imports when Nova
  imports Evo or vice-versa (e.g., via clients/gates).
"""

from __future__ import annotations

__version__ = "0.1-mvp"

__all__ = ["__version__"]
