from __future__ import annotations

from typing import Any


def _avg(vals: list[float]) -> float:
    return float(sum(vals) / len(vals)) if vals else 0.0


def headers_for_propose(candidates: list[dict] | list[Any]) -> dict[str, str]:
    # candidates may be Pydantic models or dicts
    n = len(candidates or [])
    return {
        "X-Nova-Propose-Candidates": str(n),
    }


def headers_for_evaluate(candidates: list[dict] | list[Any]) -> dict[str, str]:
    pcc_ok = 0
    pcc_fail = 0
    cost, risk, complexity, fae = [], [], [], []

    for c in candidates or []:
        cd = c if isinstance(c, dict) else getattr(c, "dict", lambda: {})()
        if not isinstance(cd, dict):
            continue
        ev = (cd.get("evidence") or {}).get("pcc") or {}
        if ev.get("ok") is True:
            pcc_ok += 1
        elif ev.get("ok") is False:
            pcc_fail += 1

        sc = cd.get("scores") or {}
        # tolerant casting
        try:
            cost.append(float(sc.get("cost_ms", 0.0) or 0.0))
        except Exception:
            pass
        try:
            risk.append(float(sc.get("risk", 0.0) or 0.0))
        except Exception:
            pass
        try:
            complexity.append(float(sc.get("complexity", 0.0) or 0.0))
        except Exception:
            pass
        try:
            fae.append(float(sc.get("fae", 0.0) or 0.0))
        except Exception:
            pass

    return {
        "X-Nova-Evaluate-Pcc-Ok": str(pcc_ok),
        "X-Nova-Evaluate-Pcc-Fail": str(pcc_fail),
        "X-Nova-Avg-Cost-Ms": f"{_avg(cost):.0f}",
        "X-Nova-Avg-Risk": f"{_avg(risk):.3f}",
        "X-Nova-Avg-Complexity": f"{_avg(complexity):.3f}",
        "X-Nova-Avg-Fae": f"{_avg(fae):.3f}",
    }


def headers_for_auction(auction_result: dict | Any) -> dict[str, str]:
    ad = (
        auction_result
        if isinstance(auction_result, dict)
        else getattr(auction_result, "dict", lambda: {})()
    )
    winners = ad.get("winners") or []
    return {
        "X-Nova-Auction-Winners": str(len(winners)),
    }
