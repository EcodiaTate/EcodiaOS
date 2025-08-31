# systems/simula/ops/glue.py
from __future__ import annotations

from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
from systems.simula.code_sim.evaluators.impact import compute_impact
from systems.simula.config.loader import load_config
from systems.simula.policy.eos_checker import check_diff_against_policies, load_policy_packs


def quick_policy_gate(diff_text: str) -> dict[str, object]:
    cfg = load_config()
    packs = load_policy_packs(cfg.eos_policy_paths) if cfg.eos_policy_paths else load_policy_packs()
    rep = check_diff_against_policies(diff_text, packs)
    return {"ok": rep.ok, "findings": rep.summary()}


def quick_impact_and_cov(diff_text: str) -> dict[str, object]:
    impact = compute_impact(diff_text)
    cov = compute_delta_coverage(diff_text).summary()
    return {"impact": {"changed": impact.changed, "k_expr": impact.k_expr}, "coverage_delta": cov}
