# systems/nova/runners/patch_handoff.py
# --- AMBITIOUS UPGRADE (NEW FILE) ---
from __future__ import annotations

from uuid import uuid4

from systems.nova.clients.simula_client import SimulaClient
from systems.nova.schemas import InnovationBrief, InventionCandidate
from systems.nova.types.patch import SimulaPatchBrief, SimulaPatchTicket


class PatchHandoff:
    """
    Transforms a winning InventionCandidate -> SimulaPatchBrief and submits to Simula.
    No codegen here; Simula owns it. [cite: 445-446]
    """

    def __init__(self) -> None:
        self._simula = SimulaClient()

    def to_brief(
        self,
        brief: InnovationBrief,
        winner: InventionCandidate,
        decision_id: str | None = None,
    ) -> SimulaPatchBrief:
        """Constructs the payload for the Simula handoff."""
        return SimulaPatchBrief(
            brief_id=f"sb_{uuid4().hex[:10]}",
            source="nova",
            candidate_id=winner.candidate_id,
            playbook=winner.playbook,
            problem=brief.problem,
            context=brief.context or {},
            mechanism_spec=winner.spec.get("mechanism_graph", {}),
            capability_spec=winner.spec.get("capability_spec", {}),
            obligations=winner.obligations or {},
            rollback_contract=winner.rollback_contract or {},
            evidence=winner.evidence or {},
            provenance={"nova_brief_id": brief.brief_id, "decision_id": decision_id or ""},
        )

    async def submit(
        self,
        patch_brief: SimulaPatchBrief,
        decision_id: str | None = None,
    ) -> SimulaPatchTicket:
        """Submits the patch brief to Simula and returns a ticket for tracking."""
        # The result from Simula's codegen endpoint is expected to be a dict
        # that can be parsed into a SimulaPatchTicket.
        simula_response = await self._simula.submit_patch(patch_brief, decision_id=decision_id)
        return SimulaPatchTicket(**simula_response)
