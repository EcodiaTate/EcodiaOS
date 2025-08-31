# core/prompting/runtime.py
# --- PROJECT SENTINEL UPGRADE ---
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Coroutine

import jinja2

# --- Core System Imports ---
from core.llm.utils import extract_json_block

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
        raise FileNotFoundError("Could not find templates.yaml. Set EOS_TEMPLATES_PATH or place it in core/prompting/")

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
}

async def _run_lenses(spec: PromptSpec, base_context: dict[str, Any]) -> dict[str, Any]:
    """Dynamically runs context lenses defined in the spec."""
    enriched_context = base_context.copy()
    for lens_name in spec.context_lenses:
        lens_func = LENS_MAP.get(lens_name)
        if not lens_func:
            continue
        
        # Simple argument binding for now
        if lens_name == "equor.identity":
            result = await lens_func(spec.identity.agent)
        elif lens_name == "retrieval.semantic":
            query = base_context.get("retrieval_query", "")
            result = await lens_func(query)
        else:
            result = await lens_func(base_context.get(lens_name.split('.')[0]))
        
        enriched_context.update(result)
    return enriched_context

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

    # --- Lenses & Context Enrichment ---
    template_context = await _run_lenses(spec, context_dict)
    template_context["task_summary"] = task_summary
    template_context["spec"] = spec
    template_context.setdefault("identity", {"agent": spec.identity.agent})
    template_context.setdefault("context", context_dict) # Pass original context too

    # --- Template Rendering ---
    system_content_parts = []
    if spec.identity.persona_partial:
        system_content_parts.append(env.get_template(spec.identity.persona_partial).render(template_context))
    for partial in spec.safety.partials:
        system_content_parts.append(env.get_template(partial).render(template_context))

    user_content_parts = []
    used_partials = []
    for partial_name in spec.partials:
        try:
            template = env.get_template(partial_name)
            user_content_parts.append(template.render(template_context))
            used_partials.append(partial_name)
        except jinja2.TemplateNotFound:
            pass

    messages: list[dict[str, str]] = [
        {"role": "system", "content": "\n\n".join(system_content_parts).strip()},
        {"role": "user", "content": "\n\n".join(user_content_parts).strip()},
    ]

    # --- Provider Overrides & Provenance ---
    overrides = ProviderOverrides(
        max_tokens=spec.budget_policy.max_tokens_fallback,
        temperature=0.1,
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
    }

    return RenderedPrompt(messages=messages, provider_overrides=overrides, provenance=provenance)


# ---------------------------------------------------------------------
# Output Parsing, Validation, and Auto-Repair
# ---------------------------------------------------------------------


async def parse_and_validate(
    spec: PromptSpec,
    resp: LLMResponse,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Parses, validates, and optionally auto-repairs an LLM's JSON output."""
    parsed: dict[str, Any] | None = None
    notes: dict[str, Any] = {"parse_mode": spec.outputs.parse_mode}

    if resp.json and isinstance(resp.json, dict):
        parsed = resp.json
    elif resp.text:
        try:
            raw_text = (resp.text or "").strip()
            if not raw_text:
                raise ValueError("LLM response was empty.")
            json_str = extract_json_block(raw_text)
            if not json_str:
                raise ValueError("No JSON block found in LLM response.")
            parsed = json.loads(json_str)
        except (JSONDecodeError, ValueError) as e:
            notes["parse_error"] = f"Failed to decode or extract JSON: {e}"

    schema_to_use = spec.outputs.schema_ or (load_schema(spec.outputs.schema_ref) if spec.outputs.schema_ref else None)
    if not schema_to_use:
        return parsed, notes

    if not parsed:
        notes["validation_error"] = "Cannot validate empty parsed object."
        return None, notes

    is_valid, validation_msg = validate_json(parsed, schema_to_use)
    notes["schema_validation"] = validation_msg
    if is_valid:
        return parsed, notes

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
    agent_name: str, broken_payload: Any, schema: dict[str, Any], error_message: str
) -> Any:
    """Asks an LLM to repair a JSON object that failed schema validation."""
    from core.utils.net_api import ENDPOINTS, get_http_client

    messages = [
        {"role": "system", "content": "You are a JSON repair tool. Your sole purpose is to correct a broken JSON object to make it conform to a provided JSON schema. Output only the corrected, valid JSON object."},
        {"role": "user", "content": f"The following JSON object is invalid. Please correct it to match the provided schema.\n\n### TARGET SCHEMA:\n```json\n{json.dumps(schema, indent=2)}\n```\n\n### VALIDATION ERROR:\n```\n{error_message}\n```\n\n### BROKEN JSON:\n```json\n{json.dumps(broken_payload, indent=2)}\n```\n\nReturn ONLY the corrected JSON object."},
    ]
    overrides = ProviderOverrides(max_tokens=4096, temperature=0.0, json_mode=True)
    
    try:
        http = await get_http_client()
        payload = {"agent_name": agent_name, "messages": messages, "provider_overrides": overrides.__dict__}
        resp = await http.post(ENDPOINTS.LLM_CALL, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json() or {}
        return data.get("json") or json.loads(extract_json_block(data.get("text", "")))
    except Exception:
        return broken_payload