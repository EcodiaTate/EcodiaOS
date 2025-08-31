# file: systems/nova/runners/auction_client.py
from __future__ import annotations

from hashlib import blake2s
from typing import Any

from ..schemas import AuctionResult, InventionCandidate


def _value(c: InventionCandidate) -> float:
    s = c.scores or {}
    return (
        float(s.get("fae", 0.0))
        + 0.05 * float(s.get("novelty", 0.0))
        - 0.10 * float(s.get("risk", 0.0))
    )


def _receipt_hash(payload: dict[str, Any]) -> str:
    h = blake2s(repr(payload).encode("utf-8")).hexdigest()
    return h[:16]


class AuctionClient:
    """
    Deterministic, budget-aware selection w/ auditable receipt:
      value = fae + 0.05*novelty - 0.10*risk
      tie-break: lower risk, higher novelty, candidate_id
    """

    async def auction(self, candidates: list[InventionCandidate], budget_ms: int) -> AuctionResult:
        if not candidates:
            return AuctionResult(
                winners=[],
                spend_ms=0,
                market_receipt={"deterministic": True, "hash": _receipt_hash({})},
            )

        ordered = sorted(
            candidates,
            key=lambda c: (
                -_value(c),
                float(c.scores.get("risk", 1.0)),
                -float(c.scores.get("novelty", 0.0)),
                c.candidate_id,
            ),
        )

        if (budget_ms or 0) <= 0:
            winners = [ordered[0].candidate_id]
            spend = int(ordered[0].scores.get("cost_ms", 0))
        else:
            winners, spend = [], 0
            for c in ordered:
                c_cost = int(c.scores.get("cost_ms", 0))
                if spend + c_cost <= budget_ms:
                    winners.append(c.candidate_id)
                    spend += c_cost

        detail = [
            {
                "candidate_id": c.candidate_id,
                "playbook": c.playbook,
                "scores": c.scores,
                "value": round(_value(c), 6),
            }
            for c in ordered
        ]
        receipt = {
            "rule": "fae+0.05*novelty-0.10*risk",
            "budget_ms": int(budget_ms or 0),
            "ranked": detail,
            "selected": winners,
        }
        receipt["hash"] = _receipt_hash(receipt)
        return AuctionResult(winners=winners, spend_ms=spend, market_receipt=receipt)
