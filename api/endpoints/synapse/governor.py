# systems/synapse/api/endpoints/governor.py
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from core.llm.bus import event_bus
from core.utils.neo.cypher_query import cypher_query
from systems.synapse.core.governor import governor
from systems.synapse.schemas import PatchProposal

logger = logging.getLogger(__name__)

governor_router = APIRouter(prefix="/governor", tags=["Synapse Governor"])


def _to_dict(model: Any) -> dict[str, Any]:
    # Pydantic v2 vs v1 compatibility
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    # Fallback best-effort
    return json.loads(json.dumps(model))


def _proposal_id(payload: dict[str, Any]) -> str:
    pid = str(payload.get("id") or "").strip()
    if pid:
        return pid
    diff = str(payload.get("diff") or "")
    h = hashlib.sha256(diff.encode("utf-8")).hexdigest()[:24]
    return f"pp_{h}"


@governor_router.post("/submit_proposal", status_code=202)
async def submit_proposal(proposal: PatchProposal):
    """
    Accept a self-upgrade proposal and submit it to the Governor's verification gauntlet.
    Emits a receipt event and persists an audit record before verification.
    """
    try:
        payload = _to_dict(proposal)
        pid = _proposal_id(payload)
        summary = str(payload.get("summary") or "upgrade")
        source_agent = str(payload.get("source_agent") or "unknown")

        logger.info(
            "[API/Governor] Proposal received id=%s agent=%s summary=%s",
            pid,
            source_agent,
            summary,
        )

        # Persist receipt/audit up-front (idempotent)
        await cypher_query(
            """
            MERGE (p:UpgradeProposal {id:$id})
            ON CREATE SET p.created_at = datetime(), p.summary = $summary, p.source_agent = $src
            ON MATCH  SET p.last_seen = datetime(), p.summary = coalesce($summary, p.summary), p.source_agent = coalesce($src, p.source_agent)
            """,
            {"id": pid, "summary": summary, "src": source_agent},
        )

        # Emit 'received' event for observability/queueing dashboards
        await event_bus.publish(
            "governor.proposal.received",
            {"proposal_id": pid, "summary": summary, "source_agent": source_agent},
        )

        # Verify and (if approved) trigger CI/CD via the core Governor
        verification_result = await governor.verify_and_apply_upgrade({**payload, "id": pid})

        logger.info(
            "[API/Governor] Verification complete id=%s status=%s",
            pid,
            verification_result.get("status"),
        )
        return verification_result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[API/Governor] submit_proposal failed.")
        raise HTTPException(status_code=500, detail=f"Governor submit failed: {e}") from e
