# core/services/equor.py
# The definitive, production-ready, and canonical client for the Equor service.

from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

# --- Core EcodiaOS Utilities ---
from core.utils.net_api import ENDPOINTS, get_http_client

# --- Canonical Schemas from Equor Source ---
from systems.equor.schemas import Attestation, ComposeRequest, ComposeResponse, InvariantCheckResult


class EquorClient:
    """
    Typed adapter for the Equor HTTP API. This client is the single source of truth
    for interacting with Equor's identity, governance, and auditing functions.
    """

    async def _request(
        self, method: str, path: str, json: dict | None = None, headers: dict | None = None
    ) -> Any:
        """A consolidated, robust HTTP request helper."""
        http = await get_http_client()
        try:
            res = await http.request(method, path, json=json, headers=headers, timeout=30.0)
            res.raise_for_status()
            # Handle potential empty responses for 202/204 status codes
            if res.status_code in [202, 204]:
                return {"status": "accepted"}
            return res.json()
        except Exception as e:
            detail = "No response body."
            try:
                detail = res.text
            except Exception:
                pass
            print(f"[EquorClient] CRITICAL ERROR calling {method} {path}: {e} :: {detail}")
            raise

    async def compose(
        self,
        agent: str,
        profile_name: str = "prod",
        episode_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ComposeResponse:
        """
        Requests a composed prompt patch from Equor based on the agent's active profile.
        """
        # Ensure an episode_id exists for auditability, as required by the endpoint.
        ep_id = episode_id or f"ep_{uuid4().hex}"

        # Build the request using the canonical Pydantic schema.
        payload = ComposeRequest(
            agent=agent,
            profile_name=profile_name,
            episode_id=ep_id,
            context=context or {},
        )

        data = await self._request(
            "POST", ENDPOINTS.EQUOR_COMPOSE, json=payload.model_dump(mode="json")
        )
        return ComposeResponse.model_validate(data)

    async def attest(self, attestation: Attestation) -> dict[str, Any]:
        """
        Submits a governance attestation to be persisted in the graph.
        """
        # The /attest endpoint expects the Attestation model directly.
        return await self._request(
            "POST", ENDPOINTS.EQUOR_ATTEST, json=attestation.model_dump(mode="json")
        )

    async def run_invariant_audit(self) -> list[InvariantCheckResult]:
        """
        Triggers a full audit of all cross-system invariants.
        """
        data = await self._request("POST", ENDPOINTS.EQUOR_INVARIANTS_AUDIT)
        return [InvariantCheckResult.model_validate(item) for item in data]


# Create a singleton instance for easy, consistent importing across the application
# e.g., `from core.services.equor import equor`
equor = EquorClient()
