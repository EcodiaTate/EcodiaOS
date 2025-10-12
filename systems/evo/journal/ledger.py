# systems/evo/journal/ledger.py
from __future__ import annotations

import json

from core.utils.neo.cypher_query import cypher_query
from systems.evo.schemas import EscalationResult, Proposal, ReplayCapsule, WhyTrace


def _neo_safe_exc(e: Exception) -> bool:
    """Checks if an exception is a non-fatal Neo4j connection issue."""
    msg = str(e).lower()
    return ("driver is not initialized" in msg) or ("init_driver" in msg)


class EvoLedger:
    """
    Write-through journal into Neo4j — tolerant when Neo4j is unavailable.
    """

    async def record_escalation(self, res: EscalationResult) -> None:
        q = """
        MERGE (d:EvoDecision {id: $did})
        SET d.brief_id = $bid, d.updated_at = timestamp()
        MERGE (e:Escalation {id: $eid})
        SET e.report = $report, e.auction = $auction, e.created_at = timestamp()
        MERGE (d)-[:HAS_ESCALATION]->(e)
        """
        try:
            # --- FIX: Call .model_dump_json() on the Pydantic models ---
            # This correctly gets the JSON string representation.
            report_json = res.report.model_dump_json()
            auction_json = res.auction.model_dump_json()

            await cypher_query(
                q,
                {
                    "did": res.decision_id,
                    "bid": res.brief_id,
                    "eid": f"esc_{res.brief_id}",
                    "report": report_json,
                    "auction": auction_json,
                },
            )
        except Exception as e:
            if not _neo_safe_exc(e):
                raise

    async def record_proposal(self, p: Proposal, decision_id: str) -> None:
        q = """
        MERGE (d:EvoDecision {id: $did})
        MERGE (p:Proposal {id: $pid})
        SET p.body = $body, p.updated_at = timestamp()
        MERGE (d)-[:HAS_PROPOSAL]->(p)
        """
        try:
            proposal_body_json = p.model_dump_json()
            await cypher_query(
                q,
                {"did": decision_id, "pid": p.proposal_id, "body": proposal_body_json},
            )
        except Exception as e:
            if not _neo_safe_exc(e):
                raise

    async def record_trace(self, t: WhyTrace) -> None:
        q = """
        MERGE (d:EvoDecision {id:$did})
        CREATE (wt:WhyTrace {stage:$stage, verdict:$verdict, details:$details, ts:$ts})
        MERGE (d)-[:HAS_TRACE]->(wt)
        """
        try:
            details_json = json.dumps(t.details)
            await cypher_query(
                q,
                {
                    "did": t.decision_id,
                    "stage": t.stage,
                    "verdict": t.verdict,
                    "details": details_json,
                    "ts": t.timestamp,
                },
            )
        except Exception as e:
            if not _neo_safe_exc(e):
                raise

    async def record_replay_capsule(self, cap: ReplayCapsule) -> None:
        q = """
        MERGE (rc:ReplayCapsule {id:$cid})
        SET rc.barcode=$barcode, rc.body=$body, rc.created_at=timestamp()
        """
        try:
            capsule_body_json = cap.model_dump_json()
            await cypher_query(
                q,
                {
                    "cid": cap.capsule_id,
                    "barcode": cap.barcode,
                    "body": capsule_body_json,
                },
            )
        except Exception as e:
            if not _neo_safe_exc(e):
                raise
