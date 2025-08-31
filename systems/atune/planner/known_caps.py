# systems/atune/planner/known_caps.py
from __future__ import annotations

import time

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.atune.knowledge.graph_interface import KnowledgeGraphInterface

_KNOWN: list[str] = []
_TTL = 120.0
_TS = 0.0
_KG = KnowledgeGraphInterface()


async def get_known_capabilities() -> list[str]:
    global _TS, _KNOWN
    now = time.time()
    if (now - _TS) < _TTL and _KNOWN:
        return list(_KNOWN)
    # Try Axon first (if you later expose /mesh/capabilities)
    try:
        http = await get_http_client()
        path = getattr(ENDPOINTS, "AXON_MESH_CAPABILITIES")
        r = await http.get(path)
        if r.status_code == 200:
            js = r.json()
            if isinstance(js, list):
                _KNOWN = [str(x) for x in js]
                _TS = now
                return list(_KNOWN)
    except Exception:
        pass
    # Fallback to KG
    try:
        if hasattr(_KG, "list_capabilities"):
            caps = await _KG.list_capabilities()
            if isinstance(caps, list):
                _KNOWN = [str(c) for c in caps]
                _TS = now
                return list(_KNOWN)
    except Exception:
        pass
    return []
