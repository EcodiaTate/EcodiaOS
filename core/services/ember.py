# core/services/ember.py

from __future__ import annotations

from typing import Any, Dict


class EmberClient:
    """
    Mock client for the Ember service.
    For now, ignores inputs and always returns a neutral affect so
    downstream systems don't crash.
    """

    async def get_affect(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "agent": "ecodia",
            "mood": "Neutral",
            "state_vector": [0.0, 0.0],
            "tags": [],
        }


# Singleton instance
ember = EmberClient()
