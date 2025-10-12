# core/prompting/runtime.py
# --- PROJECT SENTINEL UPGRADE (FULL & CORRECTED) ---
from __future__ import annotations

import hashlib
import json
import os
import time
import warnings
from collections.abc import Coroutine
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional

import jinja2

# --- Core System Imports ---
from core.llm.utils import extract_json_block  # kept for primary path

# --- Local Module Imports ---
from . import lenses
from .spec import PromptSpec, ProviderOverrides
from .validators import load_schema, validate_json

# ---------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------


@dataclass
class RenderedPrompt:
    messages: list[dict[str, str]]
    provider_overrides: ProviderOverrides
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str | None = None
    json: dict[str, Any] | None = None
    call_id: str | None = None


# ---------------------------------------------------------------------
# Template Loading & Management
# ---------------------------------------------------------------------

_TEMPLATES: dict[str, str] = {}
_JINJA_ENV: jinja2.Environment | None = None
_TEMPLATES_SRC_PATH: Path | None = None
_TEMPLATES_SRC_MTIME: float | None = None


def _locate_templates_yaml() -> Path | None:
    """Finds the external templates.yaml file in predefined locations."""
    path_env = os.environ.get("EOS_TEMPLATES_PATH")
    candidates: list[Path | None] = [
        Path(path_env) if path_env else None,
        Path("core/prompting/templates.yaml"),
        Path(__file__).parent / "templates.yaml",
    ]
    for p in candidates:
        if p and p.exists():
            return p
    return None


def _load_templates_yaml(p: Path) -> dict[str, str]:
    """Loads templates from a YAML file, handling potential errors."""
    global _TEMPLATES_SRC_PATH, _TEMPLATES_SRC_MTIME
    try:
        import yaml

        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            _TEMPLATES_SRC_PATH = p
            _TEMPLATES_SRC_MTIME = p.stat().st_mtime
            return {str(k): str(v) for k, v in data.items()}
    except Exception as e:
        print(f"[prompt.runtime] WARNING: Failed to load templates.yaml @ {p}: {e}")
    return {}


def _build_jinja_env(templates: dict[str, str]) -> jinja2.Environment:
    """Builds and configures the Jinja2 environment."""
    if jinja2 is None:
        raise RuntimeError("jinja2 is required for prompt rendering")

    class DictLoader(jinja2.BaseLoader):
        def get_source(self, environment, template):
            if template not in templates:
                raise jinja2.TemplateNotFound(template)
            return templates[template], template, lambda: True

    env = jinja2.Environment(
        loader=DictLoader(),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["tojson"] = lambda d, indent=2: json.dumps(d, default=str, indent=indent)
    return env


def _ensure_jinja_env(force_reload: bool = False) -> jinja2.Environment:
    """Initializes or reloads the Jinja2 environment from external templates."""
    global _JINJA_ENV, _TEMPLATES, _TEMPLATES_SRC_MTIME, _TEMPLATES_SRC_PATH

    if _TEMPLATES_SRC_PATH:
        try:
            mtime = _TEMPLATES_SRC_PATH.stat().st_mtime
            if mtime > (_TEMPLATES_SRC_MTIME or 0):
                force_reload = True
        except FileNotFoundError:
            force_reload = True

    if _JINJA_ENV is not None and not force_reload:
        return _JINJA_ENV

    templates_path = _locate_templates_yaml()
    if not templates_path:
        raise FileNotFoundError(
            "Could not find templates.yaml. Set EOS_TEMPLATES_PATH or place it in core/prompting/"
        )

    _TEMPLATES = _load_templates_yaml(templates_path)
    _JINJA_ENV = _build_jinja_env(_TEMPLATES)
    return _JINJA_ENV


def _template_hash() -> str:
    """Computes a hash of all loaded templates for provenance."""
    h = hashlib.blake2b(digest_size=16)
    _ensure_jinja_env()
    for key in sorted(_TEMPLATES.keys()):
        h.update(key.encode())
        h.update(b"\x00")
        h.update(_TEMPLATES[key].encode())
        h.update(b"\x00")
    return h.hexdigest()


# ---------------------------------------------------------------------
# Context Lens Runner
# ---------------------------------------------------------------------

LENS_MAP: dict[str, Coroutine] = {
    "equor.identity": lenses.lens_equor_identity,
    "atune.salience": lenses.lens_atune_salience,
    "affect": lenses.lens_affect,
    "retrieval.semantic": lenses.lens_retrieval_semantic,
    "event.canonical": lenses.lens_event_canonical,
    "tools.catalog": lenses.lens_tools_catalog,
    "ecodia.self_concept": lenses.lens_ecodia_self_concept,
    "facets.affective": lenses.lens_affective_facets,
    "facets.ethical": lenses.lens_ethical_facets,
    "lens_get_tools": lenses.lens_get_tools,
    "facets.safety": lenses.lens_safety_facets,
    "facets.mission": lenses.lens_mission_facets,
    "facets.compliance": lenses.lens_compliance_facets,
    "facets.style": lenses.lens_style_facets,
    "facets.voice": lenses.lens_voice_facets,
    "facets.philosophical": lenses.lens_philosophical_facets,
    "facets.operational": lenses.lens_operational_facets,
    "facets.epistemic_humility": lenses.lens_epistemic_facets,
    "lens_simula_advice_preplan": lenses.lens_simula_advice_preplan,
    "lens_simula_advice_postplan": lenses.lens_simula_advice_postplan,
}


async def _run_lenses(spec: PromptSpec, base_context: dict[str, Any]) -> dict[str, Any]:
    """
    Runs all lenses specified in the PromptSpec, enriches the context,
    and returns provenance about which lenses were activated.
    """
    enriched_context = base_context.copy()
    lens_provenance: dict[str, Any] = {}

    for lens_name in spec.context_lenses or []:
        lens_func = LENS_MAP.get(lens_name)
        if not lens_func:
            warnings.warn(f"PromptSpec '{spec.id}' requested unknown context_lens: '{lens_name}'")
            continue

        if lens_name == "equor.identity":
            result = await lens_func(spec.identity.agent)
        elif lens_name == "retrieval.semantic":
            query = base_context.get("retrieval_query", "")
            result = await lens_func(query)
        elif lens_name == "tools.catalog":
            result = await lens_func(base_context)
        else:
            # default: pass the namespace prefix (e.g., 'event' for 'event.canonical')
            result = await lens_func(base_context.get(lens_name.split(".")[0]))

        if isinstance(result, dict):
            enriched_context.update(result)
            if "facets" in lens_name:
                facet_key = list(result.keys())[0] if result else None
                if facet_key:
                    facet_count = len(result.get(facet_key, []))
                    if facet_count > 0:
                        lens_provenance[lens_name] = {"injected_facets": facet_count}

    enriched_context["_lens_provenance"] = lens_provenance
    return enriched_context


# ---------------------------------------------------------------------
# Helpers for robust message construction
# ---------------------------------------------------------------------


def _truncate(s: str, n: int) -> str:
    if not s:
        return ""
    s = s.strip().replace("\r", " ")
    return (s[: n - 1] + "…") if len(s) > n else s


def _build_state_header(ctx: dict[str, Any]) -> str:
    """Compact, token-cheap header that makes plan-1 context-aware even if system is dropped."""
    # Attempt to derive timing / recency from context (no hard deps)
    meta = ctx.get("metadata") or {}
    last_user = ctx.get("last_user_message") or meta.get("last_user_message") or ""
    last_assistant = ctx.get("last_assistant_message") or meta.get("last_assistant_message") or ""
    minutes_since = meta.get("minutes_since_last_msg")
    topic_shift = meta.get("topic_shift_score")

    bits = []
    if "episode_id" in meta:
        bits.append(f"[episode:{meta['episode_id']}]")
    if isinstance(minutes_since, (int, float)):
        bits.append(f"[since_last:{int(minutes_since)}m]")
    if isinstance(topic_shift, (int, float)):
        bits.append(f"[topic_shift:{float(topic_shift):.2f}]")
    if last_user:
        bits.append(f'[recent_user:"{_truncate(last_user, 120)}"]')
    if last_assistant:
        bits.append(f'[recent_assistant:"{_truncate(last_assistant, 120)}"]')

    return " ".join(bits)


def _nonempty_join(parts: list[str]) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


# ---------------------------------------------------------------------
# Rendering Pipeline
# ---------------------------------------------------------------------


async def render_prompt(
    spec: PromptSpec,
    context_dict: dict[str, Any],
    task_summary: str,
) -> RenderedPrompt:
    """Renders the final messages[] using a spec and a context dictionary."""
    env = _ensure_jinja_env()

    template_context = await _run_lenses(spec, context_dict)
    template_context["task_summary"] = task_summary
    template_context["spec"] = spec

    # Ensure minimal namespaces exist
    template_context.setdefault("atune", {})
    template_context.setdefault("equor", {})
    template_context.setdefault("affect", {})
    template_context.setdefault("event", {})
    template_context.setdefault("identity", {"agent": spec.identity.agent})
    template_context.setdefault("context", context_dict)

    lens_provenance = template_context.pop("_lens_provenance", {})

    # --- SYSTEM CONTENT ---
    system_content_parts: list[str] = []
    if spec.identity.persona_partial:
        system_content_parts.append(
            env.get_template(spec.identity.persona_partial).render(template_context)
        )
    for partial in spec.safety.partials:
        system_content_parts.append(env.get_template(partial).render(template_context))
    system_text = _nonempty_join(system_content_parts)
    if not system_text:
        # Hard guard: never send a user-only call
        system_text = (
            "You are Ecodia’s planning core. Read inputs and output one precise, valid JSON plan."
        )

    # --- USER CONTENT (partials payload) ---
    user_content_parts: list[str] = []
    used_partials: list[str] = []
    for partial_name in spec.partials:
        try:
            template = env.get_template(partial_name)
            user_content_parts.append(template.render(template_context))
            used_partials.append(partial_name)
        except jinja2.TemplateNotFound:
            # Swallow silently; provenance still records used_partials
            continue

    ctx = template_context["context"]
    if "user_input" not in ctx:
        ui = (ctx.get("metadata") or {}).get("user_input")
        if ui is not None:
            ctx["user_input"] = ui

    # Prepend compact state header to make Plan-1 context-aware even if provider drops system
    state_header = _build_state_header(ctx)
    user_text = _nonempty_join(([state_header] if state_header else []) + user_content_parts)
    if not user_text:
        user_text = (ctx.get("user_input") or "").strip()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]

    overrides = ProviderOverrides(
        max_tokens=spec.budget_policy.max_tokens_fallback,
        temperature=0.1,  # base default; Synapse may override
        json_mode=(spec.outputs.parse_mode in ("strict_json", "auto_repair")),
    )

    provenance = {
        "spec_id": spec.id,
        "spec_version": spec.version,
        "scope": spec.scope,
        "agent_name": spec.identity.agent,
        "template_hash": _template_hash(),
        "templates_used": used_partials,
        "budget_tokens": overrides.max_tokens,
        "ts": time.time(),
        "lenses_activated": lens_provenance,
        # small peek for debugging first-plan context:
        "dbg": {
            "system_head": _truncate(system_text, 200),
            "user_head": _truncate(user_text, 200),
            "available_templates": len(_TEMPLATES),
        },
    }

    return RenderedPrompt(messages=messages, provider_overrides=overrides, provenance=provenance)


# ---------------------------------------------------------------------
# Output Parsing, Validation, and Auto-Repair
# ---------------------------------------------------------------------


def extract_json_flex(text: str) -> str | None:
    """
    Robustly extract the first JSON object/array from text.
    Returns the JSON string or None.
    Strategy:
      1) Direct JSON via json.loads (fast path)
      2) Use fenced block ```json ... ```
      3) Balanced scan for first {...} or [...]
    """
    if not text:
        return None
    t = text.strip()

    # 1) Direct JSON fast path
    try:
        _ = json.loads(t)
        return t
    except Exception:
        pass

    # 2) Fenced block
    import re

    fence_re = re.compile(
        r"```(?:\s*json\s*)?\n(?P<payload>(?:\{.*?\}|\[.*?\]))\n```", re.DOTALL | re.IGNORECASE
    )
    m = fence_re.search(t)
    if m:
        return m.group("payload")

    # 3) Balanced scan (string-aware)
    def find_match(s: str, start: int, open_ch: str, close_ch: str) -> int:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(s)):
            c = s[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        return -1

    for o, c in (("{", "}"), ("[", "]")):
        start = t.find(o)
        if start != -1:
            end = find_match(t, start, o, c)
            if end != -1:
                return t[start : end + 1]

    return None


async def parse_and_validate(
    spec: PromptSpec,
    resp: LLMResponse,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Parses, validates, and optionally auto-repairs an LLM's JSON output."""
    parsed: dict[str, Any] | None = None
    notes: dict[str, Any] = {"parse_mode": spec.outputs.parse_mode}

    # Prefer provider JSON when present
    if resp.json and isinstance(resp.json, dict):
        parsed = resp.json
    elif resp.text:
        # Try primary extractor, then robust fallback
        try:
            raw_text = (resp.text or "").strip()
            if not raw_text:
                raise ValueError("LLM response was empty.")
            json_str = extract_json_block(raw_text) or extract_json_flex(raw_text)
            if not json_str:
                raise ValueError("No JSON block found in LLM response.")
            parsed = json.loads(json_str)
        except (JSONDecodeError, ValueError) as e:
            notes["parse_error"] = f"Failed to decode or extract JSON: {e}"

    # Schema validation (if specified)
    schema_to_use = spec.outputs.schema_ or (
        load_schema(spec.outputs.schema_ref) if spec.outputs.schema_ref else None
    )
    if not schema_to_use:
        return parsed, notes

    if not parsed:
        notes["validation_error"] = "Cannot validate empty parsed object."
        return None, notes

    is_valid, validation_msg = validate_json(parsed, schema_to_use)
    notes["schema_validation"] = validation_msg
    if is_valid:
        return parsed, notes

    # Auto-repair if allowed
    if spec.outputs.parse_mode == "auto_repair":
        notes["auto_repair_status"] = "attempting_repair"
        repaired = await _auto_repair(
            agent_name=spec.identity.agent,
            broken_payload=parsed,
            schema=schema_to_use,
            error_message=validation_msg,
        )
        if isinstance(repaired, dict):
            is_valid_after_repair, repair_msg = validate_json(repaired, schema_to_use)
            notes["schema_validation_after_repair"] = repair_msg
            if is_valid_after_repair:
                notes["auto_repair_status"] = "success"
                return repaired, notes

    notes.setdefault("auto_repair_status", "failed")
    return parsed, notes


async def _auto_repair(
    agent_name: str,
    broken_payload: Any,
    schema: dict[str, Any],
    error_message: str,
) -> Any:
    """Asks an LLM to repair a JSON object that failed schema validation."""
    from core.utils.net_api import ENDPOINTS, get_http_client

    messages = [
        {
            "role": "system",
            "content": (
                "You are a JSON repair tool. Correct the broken JSON to conform to the provided JSON schema. "
                "Output only the corrected JSON object, with no commentary."
            ),
        },
        {
            "role": "user",
            "content": (
                "The following JSON object is invalid. Correct it to match the provided schema.\n\n"
                "### TARGET SCHEMA:\n```json\n"
                f"{json.dumps(schema, indent=2)}\n```\n\n"
                "### VALIDATION ERROR:\n```\n"
                f"{error_message}\n```\n\n"
                "### BROKEN JSON:\n```json\n"
                f"{json.dumps(broken_payload, indent=2)}\n```\n\n"
                "Return ONLY the corrected JSON object."
            ),
        },
    ]
    overrides = ProviderOverrides(max_tokens=4096, temperature=0.0, json_mode=True)

    try:
        http = await get_http_client()
        payload = {
            "agent_name": agent_name,
            "messages": messages,
            "provider_overrides": overrides.__dict__,
        }
        r = await http.post(ENDPOINTS.LLM_CALL, json=payload, timeout=30.0)
        r.raise_for_status()
        data = r.json() or {}
        # Provider might return .json directly or .text with fenced content
        return data.get("json") or json.loads(
            extract_json_block(data.get("text", ""))
            or (extract_json_flex(data.get("text", "")) or "{}")
        )
    except Exception:
        # On any failure, return the original (caller will decide fallback)
        return broken_payload
