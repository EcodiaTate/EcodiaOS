# file: systems/evo/metrics/harvesters.py
from __future__ import annotations

from typing import Any


def _ms(headers: dict[str, str]) -> float:
    try:
        return float(headers.get("x-cost-ms") or headers.get("X-Cost-MS") or 0.0)
    except Exception:
        return 0.0


def _avg(nums: list[float]) -> float:
    return float(sum(nums) / len(nums)) if nums else 0.0


def _get_score(c: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float((c.get("scores") or {}).get(key, default))
    except Exception:
        return default


def build_nova_metrics(
    *,
    propose_headers: dict[str, str],
    evaluate_headers: dict[str, str],
    auction_headers: dict[str, str],
    propose_out: list[dict[str, Any]],
    auction_out: dict[str, Any],
) -> dict[str, Any]:
    """Conservative, SoC-clean metrics bundle for Synapse outcome."""
    winners = list(auction_out.get("winners") or [])
    return {
        "propose_ms": _ms(propose_headers),
        "evaluate_ms": _ms(evaluate_headers),
        "auction_ms": _ms(auction_headers),
        "propose_candidates": len(propose_out or []),
        "winners": len(winners),
    }


def derive_eval_metrics(evaluated: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive PCC and aggregate candidate metrics after evaluate()."""
    pcc_ok = 0
    pcc_fail = 0
    cost = []
    risk = []
    complexity = []
    fae = []

    for c in evaluated or []:
        ev = (c.get("evidence") or {}).get("pcc") or {}
        if ev.get("ok") is True:
            pcc_ok += 1
        elif ev.get("ok") is False:
            pcc_fail += 1
        # aggregates
        scores = c.get("scores") or {}
        cost.append(float(scores.get("cost_ms", 0.0) or 0.0))
        risk.append(float(scores.get("risk", 0.0) or 0.0))
        complexity.append(float(scores.get("complexity", 0.0) or 0.0))
        fae.append(float(scores.get("fae", 0.0) or 0.0))

    return {
        "evaluate_pcc_ok": pcc_ok,
        "evaluate_pcc_fail": pcc_fail,
        "avg_candidate_cost_ms": _avg(cost),
        "avg_risk": _avg(risk),
        "avg_complexity": _avg(complexity),
        "avg_fae": _avg(fae),
    }


def merge_metrics(base: dict[str, Any] | None, **named_bundles: dict[str, Any]) -> dict[str, Any]:
    out = dict(base or {})
    for _, bundle in named_bundles.items():
        for k, v in (bundle or {}).items():
            out[k] = v  # shallow merge; last-in wins
    return out
