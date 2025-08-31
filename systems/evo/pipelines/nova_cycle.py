# file: systems/evo/pipelines/nova_cycle.py
from __future__ import annotations

from typing import Any

from systems.evo.clients.nova_client import NovaClient
from systems.evo.clients.synapse_client import SynapseClient
from systems.evo.metrics.harvesters import build_nova_metrics, derive_eval_metrics, merge_metrics


async def run_nova_triplet_and_log_outcome(
    *,
    brief: dict[str, Any],
    decision_id: str,
    task_key: str,
    chosen_arm_id: str,
    budget_ms_propose: int | None = None,
    budget_ms_auction: int | None = None,
    extra_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Runs propose→evaluate→auction, harvests Nova timing/counts + evaluation aggregates,
    and logs a Synapse outcome with unified metrics (single blob).
    """
    nova = NovaClient()
    syn = SynapseClient()

    # Propose
    propose_out, h_propose = await nova.propose_with_meta(
        brief,
        budget_ms=budget_ms_propose,
        decision_id=decision_id,
    )
    # Evaluate
    evaluated, h_eval = await nova.evaluate_with_meta(propose_out)
    # Auction
    auction_out, h_auction = await nova.auction_with_meta(
        evaluated,
        budget_ms=budget_ms_auction,
        decision_id=decision_id,
    )

    # Metrics: timings/counts + evaluation-derived aggregates
    nova_base = build_nova_metrics(
        propose_headers=h_propose,
        evaluate_headers=h_eval,
        auction_headers=h_auction,
        propose_out=propose_out,
        auction_out=auction_out,
    )
    eval_agg = derive_eval_metrics(evaluated)

    base = {"chosen_arm_id": chosen_arm_id}
    merge_metrics(
        base,
        nova=nova_base,
        eval=eval_agg,
        extra=(extra_metrics or {}),
    )

    # Flatten one level for Episode.metrics shape:
    # -> {"chosen_arm_id":..., "nova": {...}, "eval": {...}, "llm": {...}, ...}
    payload_metrics = dict(base)
    payload_metrics["nova"] = nova_base
    payload_metrics["eval"] = eval_agg
    if extra_metrics:
        payload_metrics.update(extra_metrics)

    # Log outcome (uses your existing Synapse outcome ingest)
    ack = await syn.log_outcome(
        episode_id=decision_id,
        task_key=task_key,
        metrics=payload_metrics,
        chosen_arm_id=chosen_arm_id,
    )

    return {"evaluated": evaluated, "auction": auction_out, "ack": ack, "metrics": payload_metrics}
