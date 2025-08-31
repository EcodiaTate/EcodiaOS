# core/services/qora.py
# Canonical client for the Qora tool execution service.

from __future__ import annotations
from typing import Any, Dict

from core.utils.net_api import ENDPOINTS, get_http_client
import os

class QoraClient:
    """Typed adapter for the Qora tool execution HTTP API."""

    async def _request(self, method: str, path: str, json: dict | None = None) -> Dict[str, Any]:
        http = await get_http_client()
        # Qora endpoints require an API key for security
        api_key = os.getenv("QORA_API_KEY") or os.getenv("EOS_API_KEY")
        if not api_key:
            raise ValueError("QORA_API_KEY or EOS_API_KEY is not set.")
        
        headers = { "X-Qora-Key": api_key }
        
        try:
            res = await http.request(method, path, json=json, headers=headers, timeout=60.0)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"[QoraClient] CRITICAL ERROR calling {method} {path}: {e}")
            raise

    async def execute_by_query(self, query: str, args: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Asks Qora to find the best tool for a natural language query and execute it.
       
        """
        payload = {
            "query": query,
            "args": args or {}
        }
        return await self._request("POST", ENDPOINTS.QORA_ARCH_EXECUTE_BY_QUERY, json=payload)

# Singleton instance
qora = QoraClient()