# systems/nova/types/patch.py
# --- AMBITIOUS UPGRADE (NEW FILE) ---
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SimulaPatchBrief(BaseModel):
    brief_id: str
    source: str = "nova"
    # summary of the winning candidate 
    candidate_id: str 
    playbook: str 
    problem: str 
    context: dict[str, Any] = {} 
    # high-level specs, not code 
    mechanism_spec: dict[str, Any] = {} 
    capability_spec: dict[str, Any] = {} 
    obligations: dict[str, list[str]] = {} 
    rollback_contract: dict[str, Any] = {} 
    evidence: dict[str, Any] = {} 
    # trace 
    provenance: dict[str, Any] = {} 


class SimulaPatchTicket(BaseModel):
    ticket_id: str
    brief_id: str 
    status: str  # queued|running|succeeded|failed 
    notes: str | None = None 