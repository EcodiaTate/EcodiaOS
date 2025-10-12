# core/services/qora.py
# Canonical client for the Qora tool execution service.

from __future__ import annotations

import os
from typing import Any, Dict

from core.utils.net_api import ENDPOINTS, get_http_client


class QoraClient:
    """Typed adapter for the Qora tool execution HTTP API."""

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict[str, Any]:
        http = await get_http_client()
        # Qora endpoints require an API key for security
        api_key = os.getenv("QORA_API_KEY") or os.getenv("EOS_API_KEY")
        if not api_key:
            raise ValueError("QORA_API_KEY or EOS_API_KEY is not set.")

        headers = {"X-Qora-Key": api_key}

        try:
            res = await http.request(method, path, json=json, headers=headers, timeout=60.0)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"[QoraClient] CRITICAL ERROR calling {method} {path}: {e}")
            raise

    async def execute_by_query(self, query: str, args: dict[str, Any] = None) -> dict[str, Any]:
        """
        Asks Qora to find the best tool for a natural language query and execute it.

        """
        payload = {
            "query": query,
            "args": args or {},
        }
        return await self._request("POST", ENDPOINTS.QORA_ARCH_EXECUTE_BY_QUERY, json=payload)


# Singleton instance
qora = QoraClient()


class QoraClient:
    """
    A simple HTTP client to interact with the Qora dossier service.
    """

    def __init__(self):
        self.base_url = os.getenv("ECODIAOS_BASE_URL", "http://api:8000")
        self.dossier_endpoint = f"{self.base_url}/qora/dossier/build"

    async def get_dossier(self, target_fqname: str, intent: str = "implement") -> dict[str, Any]:
        """
        Fetches the multi-modal dossier for a given target FQN.
        """
        if not target_fqname:
            return {"error": "Target FQN cannot be empty"}

        http = await get_http_client()
        payload = {"target_fqname": target_fqname, "intent": intent}

        try:
            response = await http.post(self.dossier_endpoint, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            # The API wraps the result in {"ok": True, "dossier": {...}}
            return data.get("dossier", {})
        except Exception as e:
            print(f"Error fetching dossier for {target_fqname}: {e}")
            return {"error": str(e)}
