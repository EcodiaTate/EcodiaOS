from __future__ import annotations

from typing import Any


def _coerce_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _tokens_from_openai(usage: dict[str, Any]) -> tuple[int, int, int]:
    pt = int(usage.get("prompt_tokens") or usage.get("prompt_tokens_total") or 0)
    ct = int(usage.get("completion_tokens") or usage.get("completion_tokens_total") or 0)
    tt = int(usage.get("total_tokens") or (pt + ct))
    return pt, ct, tt


def _tokens_from_anthropic(usage: dict[str, Any]) -> tuple[int, int, int]:
    pt = int(usage.get("input_tokens") or 0)
    ct = int(usage.get("output_tokens") or 0)
    tt = pt + ct
    return pt, ct, tt


def extract_usage_tokens(resp: dict[str, Any]) -> tuple[int, int, int]:
    """
    Best-effort, provider-agnostic token extraction.
    Supports OpenAI/Anthropic; defaults to zeros if not present.
    """
    usage = resp.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0, 0

    # Heuristics: look for anth/openai keys
    if any(k in usage for k in ("input_tokens", "output_tokens")):
        return _tokens_from_anthropic(usage)
    return _tokens_from_openai(usage)


def build_telemetry(
    *,
    start_ts: float,
    end_ts: float,
    req_headers: dict[str, str],
    resp: dict[str, Any],
    provider_hint: str | None = None,
    model_hint: str | None = None,
) -> dict[str, Any]:
    dur_ms = int((end_ts - start_ts) * 1000.0)
    pt, ct, tt = extract_usage_tokens(resp)

    # Try to discover provider/model from known shapes
    provider = provider_hint or resp.get("provider") or resp.get("provider_name") or ""
    model = model_hint or resp.get("model") or resp.get("model_name") or ""

    # Correlation headers (budget/spec/decision are common across EOS)
    decision_id = req_headers.get("x-decision-id") or req_headers.get("X-Decision-Id") or ""
    budget_ms = req_headers.get("x-budget-ms") or req_headers.get("X-Budget-Ms") or ""
    spec_id = req_headers.get("x-spec-id") or req_headers.get("X-Spec-Id") or ""
    spec_version = req_headers.get("x-spec-version") or req_headers.get("X-Spec-Version") or ""

    telemetry = {
        "provider": str(provider),
        "model": str(model),
        "duration_ms": dur_ms,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": tt,
        "decision_id": decision_id,
        "budget_ms": budget_ms,
        "spec_id": spec_id,
        "spec_version": spec_version,
        # Pass through any provider-native usage block for raw access
        "raw_usage": resp.get("usage") if isinstance(resp.get("usage"), dict) else {},
    }
    return telemetry
