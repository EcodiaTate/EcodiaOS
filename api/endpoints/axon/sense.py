from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel  # REFACTORED: Import BaseModel

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.axon.dependencies import get_journal, get_quarantine
from systems.axon.io.quarantine import Quarantine
from systems.axon.journal.mej import MerkleJournal
from systems.axon.schemas import AxonEvent


# REFACTORED: Define a Pydantic model for the incoming request body
# -----------------------------------------------------------------
class SenseRequest(BaseModel):
    """
    Defines the expected structure for data sent to the /sense endpoint.
    Allows for known fields and arbitrary additional data.
    """

    source: str = "unknown"
    event_type: str = "generic"
    modality: str = "json"
    parsed: dict[str, Any] | None = None

    class Config:
        # Allow any other fields to be passed in the payload
        extra = "allow"


# -----------------------------------------------------------------

sense_router = APIRouter()


@sense_router.post("/sense")
async def sense(
    # REFACTORED: Use the Pydantic model for validation and documentation
    payload: SenseRequest,
    quarantine: Quarantine = Depends(get_quarantine),
    journal: MerkleJournal = Depends(get_journal),
) -> dict[str, Any]:
    """
    Quarantine -> canonical AxonEvent -> MEJ -> forward to Atune /route.
    """
    # REFACTORED: Convert the Pydantic model to a dict for existing logic
    payload_dict = payload.model_dump()

    # Basic quarantine (extend with typed reflexes as needed)
    if quarantine.is_malicious(payload_dict):
        raise HTTPException(status_code=400, detail="Payload quarantined")

    # REFACTORED: Create AxonEvent from the validated Pydantic model's data
    ev = AxonEvent(
        event_id=str(uuid.uuid4()),
        t_observed=time.time(),
        source=payload.source,
        event_type=payload.event_type,
        modality=payload.modality,
        payload_ref=None,
        # This line preserves the original logic: use the 'parsed' field if it exists,
        # otherwise use the entire payload.
        parsed=payload.parsed or payload_dict,
        embeddings={},
    )
    journal.write_entry(ev)

    client = await get_http_client()
    r = await client.post(
        ENDPOINTS.ATUNE_ROUTE,
        json=ev.model_dump(),
        headers={"x-budget-ms": "1500"},
    )
    r.raise_for_status()
    return {"status": "forwarded", "atune_result": r.json()}
