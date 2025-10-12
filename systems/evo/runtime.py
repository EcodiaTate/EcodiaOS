# systems/evo/runtime.py
from __future__ import annotations

from systems.evo.engine import EvoEngine

_engine_singleton: EvoEngine | None = None


def get_engine() -> EvoEngine:
    """
    Initializes and returns the singleton EvoEngine instance.
    This ensures all API endpoints and internal services share the same
    stateful engine components (like the in-memory conflict store).
    """
    global _engine_singleton
    if _engine_singleton is None:
        # The corrected EvoEngine now handles its own dependency composition.
        _engine_singleton = EvoEngine()
    return _engine_singleton
