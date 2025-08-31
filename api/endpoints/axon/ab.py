# api/endpoints/axon/ab.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header

from core.metrics.registry import REGISTRY
from systems.axon.ab.runner import run_ab_trial
from systems.axon.dependencies import get_journal
from systems.axon.journal.mej import MerkleJournal
from systems.axon.schemas import AxonIntent

ab_router = APIRouter()

@ab_router.post("/run")
async def run_ab(
    intent: AxonIntent,
    x_decision_id: str | None = Header(default=None),
    journal: MerkleJournal = Depends(get_journal),
) -> dict[str, Any]:
    """
    Twin + shadow dry-runs (no side effects). Results are journaled for replay.
    """
    REGISTRY.counter("axon.ab.run.calls").inc()
    trial = await run_ab_trial(intent, decision_id=x_decision_id)
    try:
        journal.write_entry({
            "type": "ab_trial",
            "intent_id": intent.intent_id,
            "capability": intent.target_capability,
            "results": trial,
            "decision_id": x_decision_id,
        })
    except Exception:
        pass
    return trial
