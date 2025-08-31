# file: systems/nova/runners/rollout_client.py
from __future__ import annotations

from systems.nova.schemas import RolloutRequest, RolloutResult


class RolloutClient:
    """
    Staged rollout stub with explicit status codes.
    Wire to Axon/Atune actuation later via drivers.
    """

    async def rollout(self, req: RolloutRequest) -> RolloutResult:
        # Gate on obligations present; otherwise reject
        if not (req.obligations or {}).get("post", []):
            return RolloutResult(status="rejected", notes="missing post-conditions")
        return RolloutResult(
            status="staged",
            driver_name="nova-stager",
            notes="awaiting shadow canary",
        )
