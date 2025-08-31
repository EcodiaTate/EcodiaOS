from __future__ import annotations

from core.utils.neo.cypher_query import cypher_query
from systems.evo.schemas import EscalationResult, Proposal, ReplayCapsule, WhyTrace
from systems.synk.core.tools.neo import add_node, add_relationship


async def write_trace(trace: WhyTrace) -> None:
    await add_node(
        labels=["EvoWhyTrace"],
        properties={
            "decision_id": trace.decision_id,
            "stage": trace.stage,
            "verdict": trace.verdict,
            "details": trace.model_dump_json(),
            "timestamp": trace.timestamp,
        },
    )


async def write_escalation(escalation: EscalationResult) -> None:
    decision_id = escalation.provenance.get("decision_id")
    brief_id = escalation.brief_id

    await add_node(
        labels=["EvoBrief"],
        properties={
            "event_id": brief_id,
            "decision_id": decision_id,
            "body": escalation.model_dump_json(),
        },
    )
    for cid in escalation.report.conflict_ids:
        await add_relationship(
            src_match={"label": "EvoBrief", "match": {"event_id": brief_id}},
            dst_match={"label": "Conflict", "match": {"event_id": cid}},
            rel_type="ESCALATES",
        )


async def write_proposal(proposal: Proposal, decision_id: str) -> None:
    pid = proposal.proposal_id
    await add_node(
        labels=["EvoProposal"],
        properties={
            "event_id": pid,
            "decision_id": decision_id,
            "title": proposal.title,
            "summary": proposal.summary,
            "risk_level": proposal.risk_level.value,
            "body": proposal.model_dump_json(),
        },
    )
    for hyp in proposal.hypotheses:
        for cid in hyp.conflict_ids:
            await add_relationship(
                src_match={"label": "EvoProposal", "match": {"event_id": pid}},
                dst_match={"label": "Conflict", "match": {"event_id": cid}},
                rel_type="ADDRESSES",
            )


async def write_replay_capsule(capsule: ReplayCapsule) -> None:
    params = {
        "decision_id": capsule.capsule_id,
        "barcode": capsule.barcode,
        "capsule_body": capsule.model_dump_json(),
    }
    await cypher_query(
        """
        MERGE (rc:EvoReplayCapsule:ReplayCapsule {id: $decision_id})
        SET rc.barcode = $barcode, rc.body = $capsule_body
        WITH rc
        MATCH (wt:EvoWhyTrace {decision_id: $decision_id})
        MERGE (rc)-[:REPRODUCES]->(wt)
        """,
        params,
    )
