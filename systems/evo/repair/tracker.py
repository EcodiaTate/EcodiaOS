from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class RepairTicket:
    ticket_id: str
    proposal_id: str
    simula_ticket_id: str
    status: str = "submitted"
    notes: str | None = None
    provenance: dict = field(default_factory=dict)


class RepairTracker:
    """
    In-memory repair tickets used by /evo/repair/* endpoints.
    """

    def __init__(self) -> None:
        self._store: dict[str, RepairTicket] = {}

    def record(self, proposal_id: str, simula_ticket_id: str, provenance: dict) -> RepairTicket:
        t = RepairTicket(
            ticket_id=f"rt_{uuid4().hex[:10]}",
            proposal_id=proposal_id,
            simula_ticket_id=simula_ticket_id,
            provenance=provenance or {},
        )
        self._store[t.ticket_id] = t
        return t

    def update(self, ticket_id: str, status: str, notes: str | None) -> RepairTicket:
        t = self._store.get(ticket_id)
        if not t:
            raise KeyError(f"Unknown ticket_id: {ticket_id}")
        t.status = status or t.status
        t.notes = notes
        return t

    def get(self, ticket_id: str) -> RepairTicket:
        t = self._store.get(ticket_id)
        if not t:
            raise KeyError(f"Unknown ticket_id: {ticket_id}")
        return t

    def list(self, proposal_id: str | None = None) -> builtins.list[RepairTicket]:
        vals = list(self._store.values())
        return [t for t in vals if (proposal_id is None or t.proposal_id == proposal_id)]
