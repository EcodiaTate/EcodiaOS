# file: systems/evo/scorecards/exporter.py
from __future__ import annotations

from hashlib import blake2s
from typing import Any


def _h(x: Any) -> str:
    return blake2s(repr(x).encode("utf-8")).hexdigest()[:16]


class ScorecardExporter:
    """
    Build an auditable, WhyTrace-friendly scorecard for an escalation:
      - conflicts, obviousness report, brief_id
      - candidate summaries, auction winners, market receipt (with hash)
      - replay capsules & barcodes when present
    """

    def build(self, escalation_result: dict[str, Any]) -> dict[str, Any]:
        report = escalation_result.get("report", {})
        candidates: list[dict[str, Any]] = escalation_result.get("candidates", []) or []
        auction: dict[str, Any] = escalation_result.get("auction", {}) or {}

        summary = [
            {
                "candidate_id": c.get("candidate_id"),
                "playbook": c.get("playbook"),
                "scores": c.get("scores"),
                "value": round(
                    float(c.get("scores", {}).get("fae", 0.0))
                    + 0.05 * float(c.get("scores", {}).get("novelty", 0.0))
                    - 0.10 * float(c.get("scores", {}).get("risk", 0.0)),
                    6,
                ),
            }
            for c in candidates
        ]
        sc = {
            "brief_id": escalation_result.get("brief_id"),
            "report": report,
            "candidates": summary,
            "winners": auction.get("winners", []),
            "market_receipt": auction.get("market_receipt", auction),
            "capsules": escalation_result.get("replay_capsules", []),
        }
        sc["hash"] = _h(sc)
        return sc
