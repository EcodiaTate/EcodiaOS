# systems/simula/code_sim/portfolio.py
# FINAL VERSION FOR PHASE II
from __future__ import annotations

from typing import Any

# REMOVED evaluation and reward imports, as this is now Synapse's job.
from systems.simula.code_sim.mutators.ast_refactor import AstMutator
from systems.simula.code_sim.mutators.prompt_patch import llm_unified_diff
from systems.simula.code_sim.telemetry import telemetry


async def _generate_single_candidate(step: Any, strategy: str) -> str | None:
    """Generates a single code modification candidate (diff) based on the chosen strategy."""
    if strategy == "llm_base":
        return await llm_unified_diff(step, variant="base")
    if strategy == "llm_creative":
        return await llm_unified_diff(step, variant="creative")
    if strategy == "ast_scaffold":
        return AstMutator(aggressive=False).mutate(step=step, mode="scaffold")
    # Add more strategies here
    return None


async def generate_candidate_portfolio(
    job_meta: dict,
    step: Any,
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
        diff = await _generate_single_candidate(step, strategy)
        if diff:
            candidate_diffs.append(diff)
            telemetry.log_event(
                "candidate_generated",
                {
                    "job_id": job_meta.get("job_id"),
                    "step": getattr(step, "name", "unknown"),
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
