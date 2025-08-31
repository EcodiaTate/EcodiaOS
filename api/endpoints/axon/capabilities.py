# api/endpoints/axon/capabilities.py
from __future__ import annotations

from fastapi import APIRouter

mesh_router = APIRouter()

# Try to read from lifecycle; fall back to env hint
try:
    from systems.axon.mesh.lifecycle import DriverLifecycleManager  # type: ignore
except Exception:
    DriverLifecycleManager = None  # type: ignore

import os


@mesh_router.get("/capabilities")
async def mesh_capabilities() -> list[str]:
    try:
        if DriverLifecycleManager is not None:
            mgr = DriverLifecycleManager()
            caps = []
            if hasattr(mgr, "list_drivers"):
                for d in mgr.list_drivers():
                    # each driver state may have .capability or .spec.capability
                    cap = getattr(d, "capability", None) or getattr(
                        getattr(d, "spec", None),
                        "capability",
                        None,
                    )
                    if cap:
                        caps.append(str(cap))
            elif hasattr(mgr, "get_all_states"):
                for st in mgr.get_all_states():
                    cap = getattr(st, "capability", None) or getattr(
                        getattr(st, "spec", None),
                        "capability",
                        None,
                    )
                    if cap:
                        caps.append(str(cap))
            if caps:
                return sorted(set(caps))
    except Exception:
        pass
    hint = os.getenv("AXON_CAPABILITIES_HINT", "")
    return [c.strip() for c in hint.split(",") if c.strip()]
