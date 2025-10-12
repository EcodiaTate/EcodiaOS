# systems/evo/clients/evo_client.py
from __future__ import annotations

import logging
from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.evo.schemas import ConflictNode

logger = logging.getLogger(__name__)


class EvoConflictClient:
    """A client for reporting conflicts to the Evo system's intake."""

    async def report_conflict(self, conflict_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Submits a single conflict node to the Evo intake endpoint.

        Args:
            conflict_payload: A dictionary conforming to the ConflictNode schema.

        Returns:
            The response from the Evo service, typically the new conflict_id.
        """
        try:
            # Validate the payload against the Pydantic model before sending
            ConflictNode.model_validate(conflict_payload)

            client = await get_http_client()
            # Assuming ENDPOINTS.EVO_CONFLICTS_CREATE points to POST /evo/conflicts/
            response = await client.post(ENDPOINTS.EVO_CONFLICTS_CREATE, json=conflict_payload)
            response.raise_for_status()
            logger.info(
                "Successfully reported conflict to Evo: %s", conflict_payload.get("conflict_id")
            )
            return response.json()
        except Exception:
            # This is a critical failure path for the immune system.
            logger.exception("CRITICAL: Failed to report conflict to Evo engine.")
            return {"error": "Failed to report conflict"}
