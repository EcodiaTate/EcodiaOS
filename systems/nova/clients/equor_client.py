# file: systems/nova/clients/equor_client.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.utils.net_api import ENDPOINTS, get_http_client


class EquorPolicyClient(BaseModel):
    """
    Equor = identity/policy authority.
    This client ONLY requests validation via the net_api overlay.
    """

    async def validate(
        self,
        payload: dict[str, Any],
        *,
        decision_id: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if decision_id:
            headers["x-decision-id"] = decision_id

        client = await get_http_client()
        r = await client.post(ENDPOINTS.EQUOR_POLICY_VALIDATE, json=payload, headers=headers)
        r.raise_for_status()
        return dict(r.json())
