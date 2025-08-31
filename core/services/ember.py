# core/services/ember.py

from __future__ import annotations
from typing import Any, Dict

from core.utils.net_api import ENDPOINTS, get_http_client

class EmberClient:
    """
    Client for the Ember service, responsible for querying Ecodia's
    internal affective state.
    """
    async def get_affect(self, agent: str = "ecodia") -> Dict[str, Any]:
        """Fetches the current mood for a given agent."""
        http = await get_http_client()
        try:
            # Use the canonical endpoint alias
            res = await http.get(ENDPOINTS.EMBER_AFFECT, params={"agent": agent})
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"[EmberClient] ERROR: Could not fetch affect, using fallback. {e}")
            return {"agent": agent, "mood": "Neutral"} # Fails safe

# Singleton instance
ember = EmberClient()