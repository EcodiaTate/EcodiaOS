from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.utils.net_api import ENDPOINTS, get_http_client


class QoraBridge(BaseModel):
    """
    Capability-detecting Qora client. No hardcoded paths.
    If an endpoint is absent in the overlay, methods degrade to no-ops.
    Expected (if present): QORA_SEARCH, QORA_EMBED, QORA_UPSERT
    """

    async def embed(self, text: str) -> list[float]:
        if not hasattr(ENDPOINTS, "QORA_EMBED"):
            return []
        http = await get_http_client()
        r = await http.post(ENDPOINTS.QORA_EMBED, json={"text": text})
        r.raise_for_status()
        return list(r.json().get("vector", []))

    async def search(
        self,
        *,
        kind: str,
        vector: list[float],
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        if not hasattr(ENDPOINTS, "QORA_SEARCH"):
            return []
        http = await get_http_client()
        r = await http.post(
            ENDPOINTS.QORA_SEARCH,
            json={"kind": kind, "vector": vector, "top_k": top_k},
        )
        r.raise_for_status()
        return list(r.json() or [])

    async def upsert(self, *, labels: list[str], properties: dict[str, Any]) -> dict[str, Any]:
        if not hasattr(ENDPOINTS, "QORA_UPSERT"):
            return {"ok": False, "reason": "QORA_UPSERT not exposed"}
        http = await get_http_client()
        r = await http.post(
            ENDPOINTS.QORA_UPSERT,
            json={"labels": labels, "properties": properties},
        )
        r.raise_for_status()
        return dict(r.json() or {"ok": True})
