# systems/simula/code_sim/portfolio.py
# REFACTORED: Standardized on passing a 'step_dict' dictionary instead of a 'step' object.
from __future__ import annotations

from typing import Any

from systems.simula.code_sim.mutators.ast_refactor import AstMutator
from systems.simula.code_sim.mutators.prompt_patch import llm_unified_diff
from systems.simula.code_sim.telemetry import telemetry


async def _generate_single_candidate(step_dict: dict[str, Any], strategy: str) -> str | None:
    """Generates a single code modification candidate (diff) based on the chosen strategy."""
    if strategy == "llm_base":
        return await llm_unified_diff(step_dict, variant="base")
    if strategy == "llm_creative":
        return await llm_unified_diff(step_dict, variant="creative")
    if strategy == "ast_scaffold":
        # Pass the dictionary directly to the mutator
        return AstMutator(aggressive=False).mutate(step_dict=step_dict, mode="scaffold")
    # Add more strategies here
    return None


async def generate_candidate_portfolio(
    job_meta: dict,
    step_dict: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Generates a portfolio of candidate diffs using various strategies.
    This function NO LONGER evaluates, scores, or ranks candidates. That is
    the sole responsibility of Synapse.
    """
    strategies = ["llm_base", "llm_creative", "ast_scaffold"]
    candidate_diffs: list[str] = []

    # --- Generate diffs for all strategies ---
    for strategy in strategies:
        diff = await _generate_single_candidate(step_dict, strategy)
        if diff:
            candidate_diffs.append(diff)
            telemetry.log_event(
                "candidate_generated",
                {
                    "job_id": job_meta.get("job_id"),
                    "step": step_dict.get("name", "unknown"),  # Access name from dict
                    "strategy": strategy,
                    "diff_size": len(diff.splitlines()),
                },
            )

    # Package the raw diffs into the content payload for Synapse
    portfolio = []
    for diff_text in set(candidate_diffs):  # Use set to de-duplicate
        portfolio.append(
            {
                "type": "unified_diff",
                "diff": diff_text,
                # In the future, add more metadata here like the source strategy
            },
        )

    return portfolio
