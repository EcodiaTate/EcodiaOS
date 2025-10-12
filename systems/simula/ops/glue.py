# systems/simula/ops/glue.py
from __future__ import annotations

import os  # MODIFIED: Imported 'os' to access environment variables

from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
from systems.simula.code_sim.evaluators.impact import compute_impact

# REMOVED: The problematic import has been deleted
# from systems.simula.config.loader import load_config
from systems.simula.policy.eos_checker import check_diff_against_policies, load_policy_packs


def quick_policy_gate(diff_text: str) -> dict[str, object]:
    """
    Checks a diff against configured policy packs.
    Policy paths are now loaded from the SIMULA_EOS_POLICY_PATHS environment variable.
    """
    # MODIFIED: Load configuration from an environment variable instead of the deleted loader.
    policy_paths_str = os.getenv("SIMULA_EOS_POLICY_PATHS")

    if policy_paths_str:
        # Assumes a comma-separated list of paths in the env var
        policy_paths = [path.strip() for path in policy_paths_str.split(",")]
        packs = load_policy_packs(policy_paths)
    else:
        # If the environment variable is not set, use the default behavior.
        packs = load_policy_packs()

    rep = check_diff_against_policies(diff_text, packs)
    return {"ok": rep.ok, "findings": rep.summary()}


def quick_impact_and_cov(diff_text: str) -> dict[str, object]:
    """
    Computes the impact analysis and delta coverage for a diff.
    This function did not require any changes.
    """
    impact = compute_impact(diff_text)
    cov = compute_delta_coverage(diff_text).summary()
    return {"impact": {"changed": impact.changed, "k_expr": impact.k_expr}, "coverage_delta": cov}
