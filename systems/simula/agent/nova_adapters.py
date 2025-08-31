# systems/simula/agent/nova_adapters.py
# UPDATED: Includes the new propose_and_auction composite tool.
from __future__ import annotations

import logging
from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.nova.schemas import (
    AuctionResult,
    InnovationBrief,
    InventionCandidate,
)
from core.utils.eos_tool import eos_tool

logger = logging.getLogger(__name__)

@eos_tool(
    name="nova.propose_solutions",
    description="Submits a high-level innovation brief to the Nova market to generate multiple potential solutions (InventionCandidates).",
    inputs={
        "type": "object",
        "properties": {
            "brief": {"type": "object", "description": "An object conforming to the InnovationBrief schema."},
            "decision_id": {"type": "string", "description": "The overarching decision ID for tracing."},
            "budget_ms": {"type": "integer", "description": "Optional budget in milliseconds for the proposal phase."}
        },
        "required": ["brief", "decision_id"]
    },
    outputs={"type": "array", "items": {"type": "object"}}
)
async def propose_solutions(brief: dict[str, Any], decision_id: str, budget_ms: int | None = 8000) -> list[dict[str, Any]]:
    """Adapter for Nova's /propose endpoint."""
    client = await get_http_client()
    headers = {"x-decision-id": decision_id, "x-budget-ms": str(budget_ms)}
    validated_brief = InnovationBrief(**brief)
    response = await client.post(ENDPOINTS.NOVA_PROPOSE, json=validated_brief.model_dump(), headers=headers)
    response.raise_for_status()
    return response.json()


@eos_tool(
    name="nova.evaluate_candidates",
    description="Submits proposed InventionCandidates to Nova's evaluation pipeline, which attaches evidence and metrics.",
    inputs={
        "type": "object",
        "properties": {
            "candidates": {"type": "array", "items": {"type": "object"}},
            "decision_id": {"type": "string"}
        },
        "required": ["candidates", "decision_id"]
    },
    outputs={"type": "array", "items": {"type": "object"}}
)
async def evaluate_candidates(candidates: list[dict[str, Any]], decision_id: str) -> list[dict[str, Any]]:
    """Adapter for Nova's /evaluate endpoint."""
    client = await get_http_client()
    headers = {"x-decision-id": decision_id}
    validated_candidates = [InventionCandidate(**c).model_dump() for c in candidates]
    response = await client.post(ENDPOINTS.NOVA_EVALUATE, json=validated_candidates, headers=headers)
    response.raise_for_status()
    return response.json()


@eos_tool(
    name="nova.auction_and_select_winner",
    description="Submits evaluated candidates to the Nova auction to select a winner based on market dynamics.",
    inputs={
        "type": "object",
        "properties": {
            "evaluated_candidates": {"type": "array", "items": {"type": "object"}},
            "decision_id": {"type": "string"}
        },
        "required": ["evaluated_candidates", "decision_id"]
    },
    outputs={"type": "object"}
)
async def auction_and_select_winner(evaluated_candidates: list[dict[str, Any]], decision_id: str) -> dict[str, Any]:
    """Adapter for Nova's /auction endpoint."""
    client = await get_http_client()
    headers = {"x-decision-id": decision_id}
    validated_candidates = [InventionCandidate(**c).model_dump() for c in evaluated_candidates]
    response = await client.post(ENDPOINTS.NOVA_AUCTION, json=validated_candidates, headers=headers)
    response.raise_for_status()
    return AuctionResult(**response.json()).model_dump()


@eos_tool(
    name="nova.propose_and_auction",
    description="A composite tool that runs the full Nova market triplet: propose, evaluate, and auction, returning the final result.",
    inputs={
        "type": "object",
        "properties": {
            "brief": {"type": "object", "description": "An object conforming to the InnovationBrief schema."},
            "decision_id": {"type": "string", "description": "The overarching decision ID for tracing."},
            "budget_ms": {"type": "integer", "description": "Optional total budget for the entire cycle."}
        },
        "required": ["brief", "decision_id"]
    },
    outputs={"type": "object"}
)
async def propose_and_auction(brief: dict[str, Any], decision_id: str, budget_ms: int | None = 15000) -> dict[str, Any]:
    """
    A powerful composite tool that encapsulates the full Nova market interaction,
    making it easier and more efficient for the Simula agent to use.
    """
    logger.info(f"[{decision_id}] Starting full Nova market cycle...")

    # 1. Propose
    candidates_raw = await propose_solutions(brief, decision_id, budget_ms)
    if not candidates_raw:
        logger.warning(f"[{decision_id}] Nova returned no candidates during propose phase.")
        return AuctionResult(winners=[], market_receipt={"status": "no_candidates"}).model_dump()
    
    logger.info(f"[{decision_id}] Nova proposed {len(candidates_raw)} candidate(s).")

    # 2. Evaluate
    evaluated_candidates_raw = await evaluate_candidates(candidates_raw, decision_id)
    logger.info(f"[{decision_id}] Evaluation complete for {len(evaluated_candidates_raw)} candidate(s).")
    
    # 3. Auction
    auction_result = await auction_and_select_winner(evaluated_candidates_raw, decision_id)
    logger.info(f"[{decision_id}] Auction complete. Winners: {auction_result.get('winners')}")
    
    return auction_result