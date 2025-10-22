# systems/synapse/policy/policy_applier.py
# COMPLETE REPLACEMENT - NOW HANDLES STYLE INJECTION

from __future__ import annotations

import logging
from typing import Any, Dict

from systems.synapse.policy.policy_dsl import (
    LLMParamsEffect,
    PolicyGraph,
    StyleInjectionEffect,
    TagBiasEffect,
    ToolBiasEffect,
)

logger = logging.getLogger(__name__)


def apply_policy_to_plan(base_plan: dict[str, Any], policy_graph: PolicyGraph) -> dict[str, Any]:
    """
    Merges the effects from a chosen PolicyGraph into a base plan or configuration object.
    """
    if not isinstance(base_plan, dict):
        logger.error("[PolicyApplier] base_plan must be a mutable dictionary.")
        return base_plan

    logger.info(f"[PolicyApplier] Applying policy '{policy_graph.id}' to plan.")

    for effect in policy_graph.effects:
        if isinstance(effect, LLMParamsEffect):
            base_plan.setdefault("llm_config", {})
            base_plan["llm_config"]["model"] = effect.model
            base_plan["llm_config"]["temperature"] = effect.temperature
            base_plan["llm_config"]["max_tokens"] = effect.max_tokens
            logger.debug(
                f"  > Applied LLMParamsEffect: model={effect.model}, temp={effect.temperature}",
            )

        elif isinstance(effect, ToolBiasEffect):
            base_plan.setdefault("tool_weights", {})
            for tool_name, weight in effect.weights.items():
                existing_weight = base_plan["tool_weights"].get(tool_name, 1.0)
                base_plan["tool_weights"][tool_name] = existing_weight * weight
            logger.debug(f"  > Applied ToolBiasEffect with weights: {effect.weights}")

        elif isinstance(effect, TagBiasEffect):
            base_plan.setdefault("applied_tags", [])
            base_plan["applied_tags"].extend(effect.tags)
            logger.debug(f"  > Applied TagBiasEffect with tags: {effect.tags}")

        elif isinstance(effect, StyleInjectionEffect):
            # NEW: Handle the style injection
            base_plan.setdefault("style", {})
            # Deep merge the style dictionary from the arm into the plan's style
            for key, value in effect.style_dict.items():
                base_plan["style"][key] = value
            logger.debug(f"  > Applied StyleInjectionEffect with style: {effect.style_dict}")

        else:
            logger.warning(f"[PolicyApplier] Unknown effect type encountered: {type(effect)}")

    # Pass the style dict up to the top level where the Jinja partial expects it
    if base_plan.get("style"):
        base_plan["arm_style"] = base_plan["style"]

    return base_plan
