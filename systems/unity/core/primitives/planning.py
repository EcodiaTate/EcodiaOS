# D:\EcodiaOS\systems\unity\core\primitives\planning.py
from __future__ import annotations

import json
from typing import Any

from core.llm.utils import extract_json_block
from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from systems.unity.schemas import DeliberationSpec


async def create_initial_plan(spec: DeliberationSpec) -> dict[str, Any]:
    """
    Derives a minimal, high-leverage program of work, guided by mission
    and operational identity facets.
    """
    corpus = [spec.topic] + [
        getattr(i, "value", "")
        for i in (spec.inputs or [])
        if isinstance(getattr(i, "value", ""), str)
    ]
    context_text = "\n".join(corpus[-6:])

    scope = "unity.planning.initial.v1"
    context = {
        "topic": spec.topic,
        "context_text": context_text,
    }
    summary = f"Create initial plan for topic: {spec.topic}"

    try:
        prompt_response = await build_prompt(
            scope=scope,
            context=context,
            summary=summary,
        )

        llm_response = await call_llm_service(
            prompt_response=prompt_response,
            agent_name="Unity.Planner",
            scope=scope,
        )

        # Prefer structured json if provided; otherwise parse from text block
        plan: Any = getattr(llm_response, "json", None)
        if not isinstance(plan, dict):
            text = getattr(llm_response, "text", "") or "{}"
            block = extract_json_block(text) or "{}"
            plan = json.loads(block)

        if not isinstance(plan, dict) or not plan.get("steps"):
            raise ValueError("LLM returned invalid or empty plan.")

    except Exception:
        # Fallback plan if prompting system fails
        plan = {
            "steps": ["Analyze inputs", "Formulate proposal", "Verify against constraints"],
            "key_risks": ["Misinterpretation of goal"],
            "success_metrics": ["Verdict is reached with high confidence"],
        }

    return plan
