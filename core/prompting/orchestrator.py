# core/prompting/orchestrator.py
# FINAL, COMPLETE, AND CORRECTED VERSION
from __future__ import annotations

import json
import uuid
import warnings
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from jinja2 import Environment  # Keep for type hinting

from core.prompting import lenses

# --- Core Prompting Imports ---
from core.prompting.registry import get_registry
from core.prompting.runtime import (
    LLMResponse,
    RenderedPrompt,
    _ensure_jinja_env,  # Import the function that provides the correct loader
    parse_and_validate,
    render_prompt,
)
from core.prompting.spec import OrchestratorResponse, PromptSpec

# --- Other Core Imports needed for restored functions ---
from core.utils.llm_gateway_client import call_llm_service

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _dig(ctx: Mapping[str, Any], *keys, default=None):
    for k in keys:
        if k in ctx and ctx[k] is not None:
            return ctx[k]
    return default


def _normalize_strategy_arm(ctx: dict[str, Any]) -> None:
    """
    Ensures BOTH:
      - ctx['strategy_arm'] is a dict with at least {'arm_id': <str>}
      - ctx['strategy_arm_id'] is a flat string
    Accepts: missing, string, dict (w/ or w/o arm_id).
    Also looks into ctx['context_vars'] / ctx['extras'] if needed.
    """

    nested_sources = []
    for k in ("context_vars", "extras"):
        v = ctx.get(k)
        if isinstance(v, dict):
            nested_sources.append(v)

    # 1) Find a candidate id
    candidate_id = None

    if isinstance(ctx.get("strategy_arm"), str):
        candidate_id = ctx["strategy_arm"]
    elif isinstance(ctx.get("strategy_arm"), dict):
        candidate_id = ctx["strategy_arm"].get("arm_id")

    if not candidate_id:
        for src in nested_sources:
            v = src.get("strategy_arm")
            if isinstance(v, str):
                candidate_id = v
                break
            if isinstance(v, dict) and v.get("arm_id"):
                candidate_id = v["arm_id"]
                break

    candidate_id = candidate_id or _dig(
        ctx,
        "strategy_arm_id",
        "selected_arm_id",
        "chosen_arm_id",
        "base_arm_id",
        default=None,
    )

    if not candidate_id:
        champ = _dig(ctx, "champion_arm", default=None)
        if isinstance(champ, dict):
            candidate_id = champ.get("arm_id")

    candidate_id = candidate_id or "unknown"

    # 2) Coerce to dict
    def _to_dict(obj: Any) -> dict[str, Any]:
        if isinstance(obj, dict):
            return {"arm_id": obj.get("arm_id", candidate_id), **obj}
        if isinstance(obj, str):
            return {"arm_id": obj}
        return {"arm_id": candidate_id}

    normalized = _to_dict(ctx.get("strategy_arm"))

    # Merge any richer nested dict without clobbering explicit keys
    for src in nested_sources:
        v = src.get("strategy_arm")
        if isinstance(v, dict):
            for k, val in v.items():
                normalized.setdefault(k, val)

    # 3) Write back stable fields the partials can rely on
    ctx["strategy_arm"] = normalized
    ctx["strategy_arm_id"] = normalized.get("arm_id", candidate_id)


def _resolve_spec(scope: str) -> PromptSpec:
    """Finds a PromptSpec in the registry by its scope."""
    reg = get_registry()
    spec = reg.get_by_scope(scope)
    if not spec:
        raise ValueError(
            f"CRITICAL: No PromptSpec found for scope '{scope}'. Ensure a spec file exists.",
        )
    return spec


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    """Recursively merges dictionaries."""
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _extract_style_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of style guidance for synthesis."""
    if isinstance(ctx.get("style"), dict):
        return dict(ctx["style"])
    pgm = ctx.get("policy_graph_meta")
    if isinstance(pgm, dict) and isinstance(pgm.get("style"), dict):
        return dict(pgm["style"])
    ps = ctx.get("plan_style")
    if isinstance(ps, dict):
        return dict(ps)
    if isinstance(ps, str):
        return {"tone": ps}
    plan = ctx.get("plan")
    if isinstance(plan, dict) and isinstance(plan.get("style"), dict):
        return dict(plan["style"])
    champ = ctx.get("champion_arm") or {}
    if isinstance(champ, dict):
        content = champ.get("content")
        if isinstance(content, dict) and isinstance(content.get("style"), dict):
            return dict(content["style"])
    return {}


def _style_to_provider_overrides(style: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Softly map style → provider overrides (temperature)."""
    if not style:
        return current
    tone = (style.get("tone") or style.get("voice") or "").lower()
    out = dict(current or {})
    temp = out.get("temperature")
    if tone in {"playful", "creative", "imaginative"}:
        temp = max(0.3, min(0.9, (temp if isinstance(temp, (int, float)) else 0.6) + 0.15))
    elif tone in {"precise", "factual", "clinical"}:
        temp = max(0.0, min(0.7, (temp if isinstance(temp, (int, float)) else 0.3) - 0.05))
    elif tone in {"warm", "empathetic"}:
        temp = max(0.3, min(0.9, (temp if isinstance(temp, (int, float)) else 0.55) + 0.05))
    if temp is not None:
        out["temperature"] = float(temp)
    return out


# --------------------------------------------------------------------------------
# Lenses registry (non-abbreviated keys for clarity)
# --------------------------------------------------------------------------------
LENS_REGISTRY = {
    # identity / concept
    "equor.identity": lenses.lens_equor_identity,
    "ecodia.self_concept": lenses.lens_ecodia_self_concept,
    # retrieval / events / state
    "retrieval.semantic": lenses.lens_retrieval_semantic,
    "event.canonical": lenses.lens_event_canonical,
    "atune.salience": lenses.lens_atune_salience,
    "affect": lenses.lens_affect,
    # tools catalogs
    "tools.catalog": lenses.lens_tools_catalog,
    "lens_get_tools": lenses.lens_get_tools,
    # facets
    "facets.safety": lenses.lens_safety_facets,
    "facets.ethical": lenses.lens_ethical_facets,
    "facets.mission": lenses.lens_mission_facets,
    "facets.style": lenses.lens_style_facets,
    "facets.voice": lenses.lens_voice_facets,
    "facets.philosophical": lenses.lens_philosophical_facets,
    "facets.epistemic_humility": lenses.lens_epistemic_facets,
    "facets.operational": lenses.lens_operational_facets,
    "facets.compliance": lenses.lens_compliance_facets,
    "facets.affective": lenses.lens_affective_facets,
    # advice retrieval — register BOTH spellings
    "lens_simula_advice_preplan": lenses.lens_simula_advice_preplan,
    "lens_simula_advice_postplan": lenses.lens_simula_advice_postplan,
}


async def _run_lens(lens_key: str, spec: PromptSpec, ctx: dict[str, Any]) -> dict[str, Any]:
    fn = LENS_REGISTRY.get(lens_key)
    if not fn:
        warnings.warn(f"Lens '{lens_key}' is defined in a spec but not found in the LENS_REGISTRY.")
        return {}

    if lens_key == "equor.identity":
        return await fn(spec.identity.agent)
    if lens_key == "retrieval.semantic":
        query = ctx.get("retrieval_query", "") or ""
        return await fn(query=query, limit=6)
    if lens_key == "event.canonical":
        return await fn(ctx.get("event") or ctx.get("canonical_event"))
    if lens_key in ("atune.salience", "affect"):
        return await fn(ctx.get(lens_key.split(".")[-1]))
    if lens_key in ("tools.catalog", "lens_get_tools"):
        return await fn(ctx)

    # advice lenses (underscore)
    if lens_key in ("lens_simula_advice_preplan", "lens_simula_advice_postplan"):
        return await fn(ctx)

    return await fn(None)


def _render_partials(partial_names: list[str], context: dict[str, Any]) -> dict[str, str]:
    """Renders a list of partial templates using the shared YAML-backed environment."""
    env = _ensure_jinja_env()
  
    # Lift commonly-used fields to top-level so partials can reference them directly.
    mem = context.get("memory")
    if mem is None and isinstance(context.get("metadata"), dict):
        mem = context["metadata"].get("memory")
    meta = context.get("metadata") or {}

    template_context = {
        # common fast-path fields
        "tools_catalog": context.get("tools_catalog", {}),
        "goal": context.get("goal"),
        "dossier": context.get("dossier", {}),
        "spec": context.get("spec"),
        # NEW: SCL context fields for new partials
        "file_cards": context.get("file_cards"),
        "tool_hints": context.get("tool_hints"),
        "history_summary": context.get("history_summary"),
        # normalized fields most partials expect:
        "strategy_arm": context.get("strategy_arm"),
        "strategy_arm_id": context.get("strategy_arm_id"),
        # NEW: expose advice directly for injection partials
        "advice_items": context.get("advice_items"),
        # Make these available at top-level for partials that reference {{ memory }} / {{ metadata }}
        "memory": mem or {},
        "metadata": meta,
        "advice_meta": context.get("advice_meta"),
        # full context (power users can read from this if needed)
        "context": context,
    }

    rendered = {}
    for name in partial_names:
        try:
            template = env.get_template(name)
            rendered[name] = template.render(template_context)
        except Exception as e:
            warnings.warn(f"Failed to render partial '{name}': {e}")
            rendered[name] = f"ERROR: Failed to render partial '{name}'."
    return rendered


def _extract_policy_params(policy_graph_meta: dict | None, spec: PromptSpec) -> dict[str, Any]:
    """Extracts LLM parameters from policy hints, with fallbacks."""
    defaults = {
        "model": "gpt-4o-mini",
        "temperature": 0.7,
        "max_tokens": spec.budget_policy.max_tokens_fallback,
        "json_mode": spec.outputs.parse_mode in ("strict_json", "auto_repair"),
    }
    if not policy_graph_meta or not isinstance(policy_graph_meta.get("effects"), list):
        return defaults
    for effect in policy_graph_meta["effects"]:
        if isinstance(effect, dict) and effect.get("type") == "LLMParamsEffect":
            return {
                "model": effect.get("model", defaults["model"]),
                "temperature": float(effect.get("temperature", defaults["temperature"])),
                "max_tokens": int(effect.get("max_tokens", defaults["max_tokens"])),
                "json_mode": defaults["json_mode"],
            }
    return defaults


def _coarse_intent(user_input: str) -> str:
    """Cheap, robust intent bucketing to prevent irrelevant tools."""
    u = (user_input or "").lower()
    authoring_keys = (
        "prompt",
        "rewrite",
        "tone",
        "style",
        "interim_thought",
        "copyedit",
        "paraphrase",
        "revise",
    )
    facts_keys = ("weather", "forecast", "news", "today", "latest", "price", "score", "schedule")
    if any(k in u for k in authoring_keys):
        return "authoring"
    if any(k in u for k in facts_keys):
        return "fresh_facts"
    return "general"


def _filter_tools_for_intent(tools_ctx: dict[str, Any], user_input: str) -> dict[str, Any]:
    """Removes irrelevant tools based on coarse intent."""
    intent = _coarse_intent(user_input)
    tools = (tools_ctx or {}).get("candidates") or []
    if intent == "authoring":
        return {"candidates": []}
    return {"candidates": tools}


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------


async def build_prompt(
    scope: str,
    context: dict[str, Any],
    summary: str = "",
    *,
    stage: str = "plan-1",
    mode: str | None = None,  # MODIFIED: Accept mode parameter
) -> OrchestratorResponse:
    """
    Builds a prompt using policy guidance already present in the context.
    This function is now a pure utility for assembling prompt components.
    """
    spec = _resolve_spec(scope)
    final_context = dict(context or {})
    final_context["spec"] = spec  # Make spec available to partials
    # Normalize memory to a top-level field for templates that expect it.
    if "memory" not in final_context and isinstance(final_context.get("metadata"), dict):
        if "memory" in final_context["metadata"]:
            final_context["memory"] = final_context["metadata"]["memory"]
    # MODIFIED: Inject the mode into the context so that mode-aware lenses like
    # `lens_get_tools` can use it for filtering.
    if mode:
        final_context["allowed_modes"] = [mode]

    policy_hints: dict[str, Any] = final_context.get("selected_policy_hints", {})
    provider_params = _extract_policy_params(policy_hints, spec)

    # Apply lenses in the order declared by the spec
    for lens_key in spec.context_lenses:
        lens_out = await _run_lens(lens_key, spec, final_context)
        _deep_merge(final_context, lens_out)

    # If no explicit tools lens, still offer catalog (Simula runner relies on it)
    if "tools.catalog" not in spec.context_lenses and "lens_get_tools" not in spec.context_lenses:
        tools_ctx = await lenses.lens_tools_catalog(final_context)
        _deep_merge(final_context, tools_ctx)

    # Intent bucketing
    user_in = (
        final_context.get("user_input")
        or (final_context.get("metadata") or {}).get("user_input")
        or ""
    )
    intent = _coarse_intent(user_in)
    final_context["intent_bucket"] = intent

    # Filter tools (Simula scopes keep full catalog)
    if scope.startswith("simula"):
        filtered_tools = final_context.get("tools_catalog", {})
    else:
        filtered_tools = _filter_tools_for_intent(final_context.get("tools_catalog", {}), user_in)
    final_context["tools_catalog"] = filtered_tools

    # Normalize strategy_arm for partials
    _normalize_strategy_arm(final_context)

    # Render partials (now includes advice_* in template context)
    if spec.partials:
        final_context["partials"] = _render_partials(spec.partials, final_context)

    # Provenance
    final_context.setdefault("metadata", {})["stage"] = stage
    final_context["metadata"]["intent_bucket"] = intent

    rendered_prompt: RenderedPrompt = await render_prompt(
        spec=spec,
        context_dict=final_context,
        task_summary=summary,
    )

    provider_overrides = {
        "model": provider_params["model"],
        "temperature": provider_params["temperature"],
        "max_tokens": provider_params["max_tokens"],
        "json_mode": provider_params["json_mode"],
        "tools": filtered_tools.get("candidates", []),
    }

    provenance = dict(rendered_prompt.provenance or {})
    provenance["intent_bucket"] = intent
    provenance["stage"] = stage
    if "episode_id" in final_context:
        provenance["synapse_episode_id"] = final_context["episode_id"]
    if "selected_arm_id" in final_context:
        provenance["synapse_arm_id"] = final_context["selected_arm_id"]
    if policy_hints:
        provenance["applied_tags"] = [
            tag
            for effect in policy_hints.get("effects", [])
            if isinstance(effect, dict) and effect.get("type") == "TagBiasEffect"
            for tag in (effect.get("tags") or [])
        ]

    return OrchestratorResponse(
        messages=rendered_prompt.messages,
        provider_overrides=provider_overrides,
        provenance=provenance,
    )


# ============================================================================
# == WORKFLOWS (Restored) ==
# ============================================================================


async def run_voxis_synthesis(context: dict[str, Any]) -> str:
    """This workflow logic should eventually be moved to a Voxis-specific service."""
    scope = "voxis.synthesis.v1"
    summary = "Synthesizing Voxis tool results into a final user-facing response."
    try:
        enriched_ctx = dict(context or {})
        style = _extract_style_from_context(enriched_ctx)
        if style:
            enriched_ctx["style"] = style
        prompt_response = await build_prompt(
            scope=scope,
            context=enriched_ctx,
            summary=summary,
            stage="synth-1",
        )
        if style:
            prompt_response.provider_overrides = _style_to_provider_overrides(
                style,
                prompt_response.provider_overrides,
            )
        llm_response = await call_llm_service(
            prompt_response=prompt_response,
            agent_name="Voxis.Synthesizer",
            scope=scope,
        )
        return (
            llm_response.text or "I have completed the action but could not formulate a response."
        )
    except Exception as e:
        warnings.warn(f"Voxis synthesis failed for scope '{scope}': {e}")
        return "I encountered an issue while formulating my response."


async def plan_deliberation(
    summary: str,
    salience_scores: dict[str, Any],
    canonical_event: dict[str, Any],
    decision_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """This workflow logic should eventually be moved to the Atune service."""

    def _looks_security_like(event: dict[str, Any]) -> bool:
        if not isinstance(event, dict):
            return False
        et = (event or {}).get("event_type", "") or ""
        parsed = (event or {}).get("parsed", {}) or {}
        tblocks = parsed.get("text_blocks", []) if isinstance(parsed, dict) else []
        t0 = tblocks[0].lower() if tblocks and isinstance(tblocks[0], str) else ""
        if et.startswith("security.") or ".audit." in et:
            return True
        crisis_terms = (
            "critical",
            "unauthorized",
            "breach",
            "intrusion",
            "violate",
            "escalation is manda",
        )
        return any(k in t0 for k in crisis_terms)

    def _coerce_json_from_llm(resp: LLMResponse) -> dict[str, Any]:
        if isinstance(resp.json, dict):
            return resp.json
        if isinstance(resp.json, list):
            try:
                return resp.json[0] if resp.json else {}
            except Exception:
                pass
        if isinstance(resp.text, str) and resp.text.strip():
            t = resp.text.strip()
            if t.startswith("```"):
                t = t.strip("`")
                if t[:4].lower() == "json":
                    t = t[4:]
            try:
                return json.loads(t)
            except Exception:
                return {}
        return {}

    def _validate_atune_choice(obj: dict[str, Any]) -> tuple[bool, str]:
        mode = obj.get("mode")
        if mode not in ("enrich_with_search", "escalate_to_unity", "discard"):
            return False, "invalid or missing 'mode'"
        if mode == "enrich_with_search" and not obj.get("search_query"):
            return False, "'search_query' required when mode == enrich_with_search"
        if mode in ("escalate_to_unity", "discard") and not obj.get("reason"):
            return False, "'reason' required when mode in {escalate_to_unity, discard}"
        return True, ""

    def _attach_whytrace(
        plan: dict[str, Any],
        prompt_resp: OrchestratorResponse,
        llm_resp: LLMResponse | None,
        notes: str | None,
    ) -> dict[str, Any]:
        plan = dict(plan or {})
        plan["_whytrace"] = {
            "provenance": prompt_resp.provenance,
            "llm_call_id": (llm_resp.call_id if llm_resp else None),
            "parse_notes": notes,
        }
        return plan

    scope = "atune.next_step.planning"
    context_dict = {
        "summary": summary,
        "salience_scores": salience_scores,
        "canonical_event": canonical_event,
        "decision_id": decision_id,
        "retrieval_query": (canonical_event or {}).get("summary", "") or summary[:160],
    }

    prompt_response: OrchestratorResponse | None = None
    try:
        prompt_response = await build_prompt(
            scope=scope,
            context=context_dict,
            summary=summary,
            stage="atune-plan",
        )
        episode_id = prompt_response.provenance.get("synapse_episode_id", str(uuid.uuid4()))
        # Force JSON mode for planner
        prompt_response.provider_overrides["json_mode"] = True
        llm_response = await call_llm_service(
            prompt_response=prompt_response,
            agent_name="Atune.Planner",
            scope=scope,
        )
    except Exception as e:
        episode_id = f"error_{uuid.uuid4()}"
        final_plan = {
            "mode": "discard",
            "reason": f"An unexpected error occurred in the planner: {e}",
        }
        dummy_prompt_response = (
            OrchestratorResponse(messages=[], provider_overrides={}, provenance={"error": str(e)})
            if prompt_response is None
            else prompt_response
        )
        return _attach_whytrace(final_plan, dummy_prompt_response, None, str(e)), episode_id

    # Parse and validate against the spec
    spec = _resolve_spec(scope)
    parsed_plan, notes = await parse_and_validate(spec, llm_response)

    if not parsed_plan:
        # Tolerant fallback: coerce JSON from raw text
        obj = {}
        try:
            if isinstance(llm_response.json, dict):
                obj = llm_response.json
            elif isinstance(llm_response.json, list) and llm_response.json:
                obj = llm_response.json[0]
            elif isinstance(llm_response.text, str) and llm_response.text.strip():
                t = llm_response.text.strip()
                if t.startswith("```"):
                    t = t.strip("`")
                    if t[:4].lower() == "json":
                        t = t[4:]
                obj = json.loads(t)
        except Exception:
            obj = {}

        # Validate minimal contract
        def _validate(obj_: dict[str, Any]) -> tuple[bool, str]:
            mode = obj_.get("mode")
            if mode not in ("enrich_with_search", "escalate_to_unity", "discard"):
                return False, "invalid or missing 'mode'"
            if mode == "enrich_with_search" and not obj_.get("search_query"):
                return False, "'search_query' required when mode == enrich_with_search"
            if mode in ("escalate_to_unity", "discard") and not obj_.get("reason"):
                return False, "'reason' required when mode in {escalate_to_unity, discard}"
            return True, ""

        ok, err = _validate(obj)
        if ok:
            final_plan = obj
        else:
            # Fail closed for likely security signals
            if _looks_security_like(canonical_event):
                final_plan = {
                    "mode": "escalate_to_unity",
                    "reason": f"Planner output error: {err}; failing closed.",
                }
            else:
                final_plan = {"mode": "discard", "reason": f"Planner output error: {err}"}
    else:
        final_plan = parsed_plan

    return _attach_whytrace(
        final_plan, prompt_response, llm_response, json.dumps(notes)
    ), episode_id
