# systems/atune/causal/scm_consumer.py
from __future__ import annotations

from typing import Any

from systems.synapse.sdk.causal_client import SynapseCausalClient


class SCMConsumer:
    """
    Read-only accessor for Synapse-produced SCM snapshots.
    """

    def __init__(self) -> None:
        self._client = SynapseCausalClient()

    async def load(self, domain: str, version: str | None = None) -> dict[str, Any] | None:
        return await self._client.get_scm_snapshot(domain=domain, version=version)
