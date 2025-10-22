# systems/evo/routing/router.py
# NEW FILE: Centralizes Evo's outbound communication.
from __future__ import annotations

from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client


class RouterService:
    """
    Thin bridge from Evo to first-party services using ENDPOINTS only,
    ensuring Evo does not have direct clients to every other system.
    """

    async def request_deliberation(
        self,
        brief_dict: dict[str, Any],
        decision_id: str,
        budget_ms: int | None,
    ) -> dict[str, Any]:
        """Routes a high-stakes decision to Atune for Unity escalation."""
        http = await get_http_client()
        headers: dict[str, str] = {"x-decision-id": decision_id}
        if budget_ms is not None:
            headers["x-budget-ms"] = str(int(budget_ms))
        r = await http.post(ENDPOINTS.ATUNE_ESCALATE, json=brief_dict, headers=headers)
        r.raise_for_status()
        return dict(r.json() or {})

    async def publish_attention_bid(
        self,
        event: dict[str, Any],
        decision_id: str,
    ) -> dict[str, Any]:
        """Publishes a scorecard or other artifact to Atune's event route."""
        http = await get_http_client()
        headers: dict[str, str] = {"x-decision-id": decision_id}
        r = await http.post(ENDPOINTS.ATUNE_ROUTE, json={"event": event}, headers=headers)
        r.raise_for_status()
        return dict(r.json() or {})

    async def verify_policy_attestation(self, policy_names: list[str], decision_id: str) -> bool:
        """Checks with Equor if a set of policies are attested."""
        http = await get_http_client()
        attestation = {
            "agent": "evo",
            "capability": "propose_solution",
            "policy_names": policy_names,
            "context": {"decision_id": decision_id},
        }
        r = await http.post(ENDPOINTS.EQUOR_ATTEST, json=attestation)
        r.raise_for_status()
        return bool((r.json() or {}).get("status") == "accepted")
