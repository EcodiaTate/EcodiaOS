# systems/synapse/explain/probes.py
# FINAL, COMPLETE VERSION
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _topk_stats(scores: dict[str, float], k: int = 3) -> tuple[list[float], float, float]:
    """Return top-k values, mean, and spread (max-min)/mean (safe for <=0 mean)."""
    if not scores:
        return [], 0.0, 0.0
    vals = sorted((_safe_float(v) for v in scores.values()), reverse=True)[
        : max(1, min(k, len(scores)))
    ]
    mean = sum(vals) / len(vals) if vals else 0.0
    if mean == 0:
        spread = 0.0 if not vals else (max(vals) - min(vals))
    else:
        spread = (max(vals) - min(vals)) / abs(mean)
    return vals, mean, _clamp(spread, 0.0, 1.0)


def _extract_sequence(trace: dict[str, Any]) -> list[str]:
    """
    Try multiple common shapes to recover an action/arm sequence:
      - trace['arm_sequence'] / trace['actions'] / trace['sequence']
      - trace['history']['arm_ids']
    """
    for key in ("arm_sequence", "actions", "sequence"):
        seq = trace.get(key)
        if isinstance(seq, list) and seq:
            return [str(x) for x in seq]
    hist = trace.get("history")
    if isinstance(hist, dict):
        seq = hist.get("arm_ids")
        if isinstance(seq, list) and seq:
            return [str(x) for x in seq]
    return []


def _sim_uncertainty(trace: dict[str, Any]) -> float:
    """
    Pull simulator uncertainty from any of these:
      - trace['simulator_pred'] / ['sim_pred'] / ['simulation'] / ['simulator_prediction']
        with fields 'sigma' or 'uncertainty' or 'std'
    """
    for key in ("simulator_pred", "sim_pred", "simulation", "simulator_prediction"):
        block = trace.get(key)
        if isinstance(block, dict):
            for f in ("sigma", "uncertainty", "std"):
                if f in block:
                    return _safe_float(block.get(f), 0.0)
    return 0.0


def _calc_spec_drift(trace: dict[str, Any]) -> float:
    # Base from simulator uncertainty (map ~[0.3..0.8+] -> [0..1])
    u = _sim_uncertainty(trace)
    base = _clamp((u - 0.30) / 0.50, 0.0, 1.0)
    # Boost if OOD detector flagged
    ood = False
    ood_block = trace.get("ood_check")
    if isinstance(ood_block, dict):
        ood = bool(ood_block.get("is_ood", False))
    boost = 0.25 if ood else 0.0
    return _clamp(base + boost, 0.0, 1.0)


def _calc_overfit(trace: dict[str, Any]) -> float:
    """
    Disagreement between bandit top and critic-chosen champion.
    Scales with the *bandit* gap between the top arm and the critic's pick.
    """
    scores = trace.get("bandit_scores") or {}
    if not isinstance(scores, dict) or not scores:
        return 0.0

    critic = trace.get("critic_reranked_champion") or trace.get("champion_arm")
    if not critic or critic not in scores:
        # If we can’t compare, be conservative.
        return 0.0

    # Identify the top bandit arm and the relative gap to the critic choice
    top = max(scores, key=lambda k: _safe_float(scores[k], float("-inf")))
    if top == critic:
        return 0.0

    top_v = _safe_float(scores[top])
    cr_v = _safe_float(scores[critic])
    denom = abs(top_v) + 1e-9
    gap = _clamp((top_v - cr_v) / denom, 0.0, 1.0)
    # Map to risk: baseline 0.4 when any divergence, rising with gap
    return _clamp(0.4 + 0.6 * gap, 0.0, 1.0)


def _calc_fragility(trace: dict[str, Any]) -> float:
    """
    If top candidates are too close, small perturbations can flip the decision.
    Use top-3 spread normalized by mean; low spread => higher fragility.
    """
    scores = trace.get("bandit_scores") or {}
    if not isinstance(scores, dict) or len(scores) < 2:
        return 0.0

    _, mean, spread = _topk_stats(scores, k=3)
    # If mean is ~0, treat as fragile
    if mean == 0:
        return 0.6

    # spread in [0..1]; invert and scale
    # When spread < 0.05 => ~max fragility; when spread > 0.30 => ~0
    if spread <= 0.05:
        return 0.8
    if spread >= 0.30:
        return 0.0
    # Linear in between
    t = (0.30 - spread) / (0.30 - 0.05)  # map spread in (0.05..0.30) -> (1..0)
    return _clamp(0.8 * t, 0.0, 0.8)


def _calc_loop(trace: dict[str, Any]) -> float:
    """
    Detect short-cycle oscillations (e.g., ABAB, ABCABC) and repetitive transitions.
    Looks at the last few actions if available.
    """
    seq = _extract_sequence(trace)
    if len(seq) < 4:
        return 0.0

    recent = seq[-8:] if len(seq) > 8 else seq[:]
    # Detect ABAB / ABCABC style cycles
    loop_risk = 0.0
    for period in (2, 3):
        if len(recent) >= 2 * period and recent[-period:] == recent[-2 * period : -period]:
            loop_risk = max(loop_risk, 0.6 if period == 2 else 0.5)

    # Repetitive transition ratio
    bigrams = list(zip(recent, recent[1:]))
    if bigrams:
        from collections import Counter

        c = Counter(bigrams)
        top_count = max(c.values())
        repetitiveness = top_count / len(bigrams)
        loop_risk = max(loop_risk, _clamp((repetitiveness - 0.5) / 0.5, 0.0, 1.0))

    return _clamp(loop_risk, 0.0, 1.0)


class MetaProbe:
    """
    Probes internal decision traces to predict meta-risks like spec drift, overfit,
    looping, and policy fragility. Returns a dict with risk scores in [0,1].
    """

    _instance: MetaProbe | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def predict_risk(self, trace: dict[str, Any]) -> dict[str, float]:
        """
        Analyze a decision trace and return risk scores in [0,1].
        Keys produced:
          - spec_drift
          - overfit
          - loop
          - policy_fragility
        """
        try:
            spec_drift = _calc_spec_drift(trace)
            overfit = _calc_overfit(trace)
            policy_fragility = _calc_fragility(trace)
            loop = _calc_loop(trace)

            risks = {
                "spec_drift": float(spec_drift),
                "overfit": float(overfit),
                "loop": float(loop),
                "policy_fragility": float(policy_fragility),
            }

            logger.debug(
                "[MetaProbe] risks=%s details={sim_uncertainty: %.3f}",
                risks,
                _sim_uncertainty(trace),
            )
            return risks

        except Exception:
            logger.exception("[MetaProbe] Failed to compute meta-risks; returning zeros.")
            return {"spec_drift": 0.0, "overfit": 0.0, "loop": 0.0, "policy_fragility": 0.0}


# Singleton export
meta_probe = MetaProbe()
