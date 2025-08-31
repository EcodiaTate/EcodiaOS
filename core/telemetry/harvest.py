from __future__ import annotations

from collections.abc import Mapping
from typing import Any

Number = int | float

# ---- helpers ---------------------------------------------------------------


def _to_int(x: str | None) -> int | None:
    try:
        return int(x) if x is not None else None
    except Exception:
        return None


def _to_float(x: str | None) -> float | None:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


def _set(d: dict[str, Any], path: str, value: Any) -> None:
    if value is None:
        return
    cur = d
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _add(d: dict[str, Any], path: str, value: Number | None) -> None:
    if value is None:
        return
    cur = d
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = (cur.get(parts[-1], 0) or 0) + value  # additive counter


# ---- main ------------------------------------------------------------------


def harvest_headers(
    headers: Mapping[str, str],
    *,
    service_hint: str | None = None,
) -> dict[str, Any]:
    """
    Convert standard response headers into a namespaced Episode.metrics blob.
    Defensive: missing fields are simply omitted.
    """
    H = {k.lower(): v for k, v in headers.items()}
    out: dict[str, Any] = {}

    # Correlation
    _set(out, "correlation.decision_id", H.get("x-decision-id"))
    _set(out, "correlation.spec_id", H.get("x-spec-id"))
    _set(out, "correlation.spec_version", H.get("x-spec-version"))
    _set(out, "correlation.arm_id", H.get("x-arm-id"))
    _set(out, "correlation.call_id", H.get("x-call-id"))
    _set(out, "correlation.budget_ms", _to_int(H.get("x-budget-ms")))

    # Universal cost
    cost_ms = _to_float(H.get("x-cost-ms"))

    # LLM family
    if ("x-llm-provider" in H) or service_hint == "llm":
        _set(out, "llm.provider", H.get("x-llm-provider"))
        _set(out, "llm.model", H.get("x-llm-model"))
        _set(out, "llm.prompt_tokens", _to_int(H.get("x-llm-prompt-tokens")))
        _set(out, "llm.completion_tokens", _to_int(H.get("x-llm-completion-tokens")))
        _set(out, "llm.total_tokens", _to_int(H.get("x-llm-total-tokens")))
        # Prefer explicit latency header, then fall back to X-Cost-MS
        _set(out, "llm.llm_latency_ms", _to_float(H.get("x-llm-latency-ms")) or cost_ms)

    # Nova family
    if "x-nova-propose-candidates" in H or service_hint in {
        "nova.propose",
        "nova.evaluate",
        "nova.auction",
    }:
        # propose
        if service_hint == "nova.propose" or "x-nova-propose-candidates" in H:
            _add(out, "nova.propose_ms", cost_ms)
            _set(out, "nova.propose_candidates", _to_int(H.get("x-nova-propose-candidates")))
        # evaluate
        if (
            service_hint == "nova.evaluate"
            or "x-nova-evaluate-pcc-ok" in H
            or "x-nova-avg-cost-ms" in H
        ):
            _add(out, "nova.evaluate_ms", cost_ms)
            _add(out, "eval.evaluate_pcc_ok", _to_int(H.get("x-nova-evaluate-pcc-ok")))
            _add(out, "eval.evaluate_pcc_fail", _to_int(H.get("x-nova-evaluate-pcc-fail")))
            _set(out, "eval.avg_candidate_cost_ms", _to_float(H.get("x-nova-avg-cost-ms")))
            _set(out, "eval.avg_risk", _to_float(H.get("x-nova-avg-risk")))
            _set(out, "eval.avg_complexity", _to_float(H.get("x-nova-avg-complexity")))
            _set(out, "eval.avg_fae", _to_float(H.get("x-nova-avg-fae")))
        # auction
        if service_hint == "nova.auction" or "x-nova-auction-winners" in H:
            _add(out, "nova.auction_ms", cost_ms)
            _set(out, "nova.winners", _to_int(H.get("x-nova-auction-winners")))

    # Axon
    if "x-axon-action-cost-ms" in H or service_hint == "axon.act":
        _set(out, "axon.action_cost_ms", _to_float(H.get("x-axon-action-cost-ms")) or cost_ms)

    return out


def merge_metrics(dest: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    """
    Deep, additive merge. Numbers are added for known counters; non-dict values overwrite.
    """
    for k, v in src.items():
        if isinstance(v, dict):
            dest[k] = merge_metrics(dest.get(k, {}), v)
        else:
            if isinstance(v, int | float) and isinstance(dest.get(k), int | float):
                # additive when both numeric
                dest[k] = dest[k] + v  # type: ignore
            else:
                dest[k] = v
    return dest
