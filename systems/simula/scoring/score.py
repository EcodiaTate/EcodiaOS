# systems/simula/scoring/score.py
from __future__ import annotations


def composite_score(evidence: dict[str, object]) -> float:
    """
    Combine hygiene, coverage Δ, security/policy, and (optional) mutation score into [0,1].
    """
    hyg = evidence.get("hygiene", {})
    static_ok = 1.0 if hyg.get("static") == "success" else 0.0
    tests_ok = 1.0 if hyg.get("tests") == "success" else 0.0
    cov = float(evidence.get("coverage_delta", {}).get("pct_changed_covered", 0.0)) / 100.0
    policy = evidence.get("policy", {"ok": True})
    policy_ok = 1.0 if policy.get("ok", True) else 0.0
    mut = float(evidence.get("mutation", {}).get("score", 1.0))
    # weights tuned for conservatism
    return 0.28 * static_ok + 0.32 * tests_ok + 0.20 * cov + 0.12 * policy_ok + 0.08 * mut
