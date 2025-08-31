# file: systems/nova/clients/synapse_client.py
from __future__ import annotations

import os
from typing import Any

import httpx

BASE_URL = os.getenv("SYNAPSE_BASE_URL", "")
TIMEOUT = float(os.getenv("ECODIAOS_HTTP_TIMEOUT", "60.0"))


class SynapseBudgetClient:
    """
    Optional budget consult (ONLY if env allows).
    Synapse remains the sole owner of learning/budgets.
    """

    def __init__(self) -> None:
        self.enabled = bool(os.getenv("NOVA_ALLOW_BUDGET_FALLBACK", "0") == "1" and BASE_URL)
        self.base_url = BASE_URL

    async def allocate_budget_ms(self, brief: dict[str, Any]) -> int:
        if not self.enabled:
            return 0
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{self.base_url}/synapse/budget/allocate", json={"brief": brief})
            r.raise_for_status()
            js = r.json()
            return int(js.get("budget_ms", 0))
