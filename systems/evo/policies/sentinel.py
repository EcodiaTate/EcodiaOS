from __future__ import annotations

from systems.evo.routing.router import RouterService


class PolicySentinel:
    """
    Ensures an evolution step sits within Equor's policy envelope
    before EVO attempts local action or publishes a market bid.
    """

    def __init__(self, router: RouterService | None = None) -> None:
        self._router = router or RouterService()

    async def verify(self, decision_id: str, required_policies: list[str]) -> bool:
        # Uses RouterService → ENDPOINTS.EQUOR_ATTEST (no guessed endpoints)
        return await self._router.verify_policy_attestation(required_policies, decision_id)
