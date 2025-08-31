# systems/simula/code_sim/equor_bridge.py
# DEPRECATED BRIDGE — kept as a soft-compat shim (no hard Equor imports)

from __future__ import annotations

import os
from typing import Any


# Try modern identity surface first; fall back to env only
def _current_identity_id() -> str:
    # Prefer explicit runtime identity if your new API is available
    try:
        from systems.equor.client import get_current_identity  # type: ignore

        ident = get_current_identity()
        if isinstance(ident, dict) and ident.get("id"):
            return str(ident["id"])
    except Exception:
        pass
    # Fallbacks
    return os.getenv("IDENTITY_ID", "ecodia.system")


async def fetch_identity_context(spec: str) -> dict[str, Any]:
    """Lightweight identity context for planning prompts (kept for legacy callsites)."""
    return {
        "identity_id": _current_identity_id(),
        "spec_preview": (spec or "")[:4000],
    }


# Legacy names preserved for callers; no-ops if old modules are gone
def resolve_equor_for_agent(*_args, **_kwargs):
    return {"status": "deprecated", "reason": "equor_bridge is a shim; use new Equor client APIs."}


def log_call_result(*_args, **_kwargs):
    return None


__all__ = ["fetch_identity_context", "resolve_equor_for_agent", "log_call_result"]
