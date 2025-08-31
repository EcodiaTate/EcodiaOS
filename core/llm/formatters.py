# core/utils/llm/formatters.py
from __future__ import annotations

import warnings
from typing import Any, Literal, TypedDict, cast

# --- Type Definitions for Clarity and Safety ---
Provider = Literal["openai", "anthropic", "gemini", "google"]


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


# Our universal tool spec shape (matches what we surface to prompts/Qora)
# name, description, parameters (JSON Schema), optional returns (JSON Schema)
class ToolSpec(TypedDict, total=False):
    name: str
    description: str
    parameters: dict
    returns: dict


def _normalize_provider(name: str) -> Provider:
    name = (name or "").lower().strip()
    if name == "google":
        return "gemini"
    if name in ("openai", "anthropic", "gemini"):
        return cast(Provider, name)
    return cast(Provider, "openai")


def _sanitize_messages(messages: list[dict[str, Any]]) -> list[ChatMessage]:
    valid_roles = {"user", "assistant", "system"}
    out: list[ChatMessage] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in valid_roles and isinstance(content, str) and content.strip():
            out.append(cast(ChatMessage, {"role": cast(Any, role), "content": content}))
    return out


def _split_system(messages: list[ChatMessage]) -> tuple[str, list[ChatMessage]]:
    """Return (system_prompt, messages_without_system). Keep the FIRST system message as system_prompt."""
    system_prompt = ""
    remainder: list[ChatMessage] = []
    for m in messages:
        if m["role"] == "system" and not system_prompt:
            system_prompt = m["content"]
            continue
        remainder.append(m)
    return system_prompt, remainder


# ----------------------- Tool spec translations -----------------------


def _to_openai_tools(tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    out = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", "")[:1024],
                    "parameters": t.get("parameters", {}) or {"type": "object", "properties": {}},
                },
            },
        )
    return out


def _to_anthropic_tools(tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    out = []
    for t in tools:
        out.append(
            {
                "name": t["name"],
                "description": t.get("description", "")[:1024],
                "input_schema": t.get("parameters", {}) or {"type": "object", "properties": {}},
            },
        )
    return out


def _to_gemini_tools(tools: list[ToolSpec] | None) -> dict[str, Any] | None:
    if not tools:
        return None
    decl = []
    for t in tools:
        decl.append(
            {
                "name": t["name"],
                "description": t.get("description", "")[:1024],
                "parameters": t.get("parameters", {}) or {"type": "object", "properties": {}},
            },
        )
    return {"function_declarations": decl}


def _map_tool_choice(
    provider: Provider,
    tool_choice: str | None,
    tools: list[ToolSpec] | None,
) -> dict[str, Any]:
    """
    tool_choice can be: None| "auto" | "none" | "<tool_name>"
    Return provider-specific extras.
    """
    tool_choice = (tool_choice or "auto").lower()
    if provider == "openai":
        if tool_choice == "none":
            return {"tool_choice": "none"}
        if tool_choice == "auto":
            return {"tool_choice": "auto"}
        return {"tool_choice": {"type": "function", "function": {"name": tool_choice}}}
    if provider == "anthropic":
        # Claude Messages API: {"tool_choice": {"type":"auto"|"any"|"tool", "name":...}}
        if tool_choice == "none":
            return {
                "tool_choice": {"type": "auto"},
            }  # no strict 'none'; emulate by auto + no tools call
        if tool_choice == "auto":
            return {"tool_choice": {"type": "auto"}}
        return {"tool_choice": {"type": "tool", "name": tool_choice}}
    if provider == "gemini":
        # Gemini needs tool_config.function_calling_config
        cfg = {"mode": "AUTO"}
        if tool_choice == "none":
            cfg = {"mode": "NONE"}
        elif tool_choice not in ("auto", "none"):
            cfg = {"mode": "ANY", "allowed_function_names": [tool_choice]}
        return {"tool_config": {"function_calling_config": cfg}}
    return {}


# ----------------------- JSON mode / schema routing -----------------------


def _json_mode_for_provider(
    provider: Provider,
    json_mode: bool,
    response_json_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    if not json_mode and not response_json_schema:
        return {}

    if provider == "openai":
        if response_json_schema:
            # If you have a schema, you can use JSON Schema response format.
            return {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_json_schema.get("title", "structured_result"),
                        "schema": response_json_schema,
                        "strict": True,
                    },
                },
            }
        # Fallback to generic json_object
        return {"response_format": {"type": "json_object"}}

    if provider == "anthropic":
        # Anthropic doesn't have a response_format knob; rely on system guardrails.
        # We still expose a metadata hint for downstream/middleware.
        return {"metadata": {"json_mode": True, "response_schema": response_json_schema or {}}}

    if provider == "gemini":
        # Gemini: prefer MIME type approach; schema can be passed via safety-checkers or in-context.
        cfg: dict[str, Any] = (
            {"response_mime_type": "application/json"}
            if (json_mode or response_json_schema)
            else {}
        )
        return {"generation_config": cfg} if cfg else {}

    return {}


# ----------------------- Core entrypoint -----------------------


def format_messages_for_provider(
    provider_name: Provider,
    system_prompt: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[ToolSpec] | None = None,
    tool_choice: str | None = None,  # "auto" | "none" | "<tool_name>"
    json_mode: bool = False,
    response_json_schema: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """
    Prepare a robust provider payload:
      - Sanitizes messages
      - Injects/positions system prompt correctly
      - Translates tool specs
      - Applies JSON mode / response schema when available
      - Maps generic knobs (max_tokens, temperature)

    Returns a kwargs dict consumable by the provider SDK or an adapter.
    """
    provider = _normalize_provider(provider_name)

    # Sanitize & split system
    sanitized = _sanitize_messages(messages)
    # If caller already embedded a system message in messages, prefer it over the explicit system_prompt arg.
    embedded_system, chat = _split_system(sanitized)
    system_text = (embedded_system or system_prompt or "").strip()

    # Provider-specific
    if provider == "anthropic":
        payload: dict[str, Any] = {
            "system": system_text or None,
            "messages": [m for m in chat if m["role"] in ("user", "assistant")],
        }
        if tools:
            payload["tools"] = _to_anthropic_tools(tools)
            payload.update(_map_tool_choice(provider, tool_choice, tools))
        # knobs
        if max_tokens is not None:
            payload["max_output_tokens"] = int(max_tokens)
        if temperature is not None:
            payload["temperature"] = float(temperature)
        # json mode/schema
        payload.update(_json_mode_for_provider(provider, json_mode, response_json_schema))
        return payload

    if provider == "openai":
        msgs = [{"role": "system", "content": system_text}] if system_text else []
        msgs.extend([m for m in chat if m["role"] in ("user", "assistant")])
        payload = {"messages": msgs}
        if tools:
            payload["tools"] = _to_openai_tools(tools)
            payload.update(_map_tool_choice(provider, tool_choice, tools))
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        if temperature is not None:
            payload["temperature"] = float(temperature)
        payload.update(_json_mode_for_provider(provider, json_mode, response_json_schema))
        return payload

    if provider == "gemini":
        # Convert to Gemini "contents" format; system is separate "system_instruction"
        def _to_gemini_contents(ms: list[ChatMessage]) -> list[dict[str, Any]]:
            role_map = {"user": "user", "assistant": "model"}
            out: list[dict[str, Any]] = []
            for m in ms:
                if m["role"] == "system":
                    # system handled separately
                    continue
                out.append({"role": role_map[m["role"]], "parts": [{"text": m["content"]}]})
            return out

        payload: dict[str, Any] = {
            "system_instruction": system_text or "",
            "contents": _to_gemini_contents(
                [m for m in chat if m["role"] in ("user", "assistant")],
            ),
        }
        if tools:
            payload["tools"] = _to_gemini_tools(tools)
            payload.update(_map_tool_choice(provider, tool_choice, tools))
        # Generation config (map both)
        gen_cfg: dict[str, Any] = {}
        if max_tokens is not None:
            gen_cfg["max_output_tokens"] = int(max_tokens)
        if temperature is not None:
            gen_cfg["temperature"] = float(temperature)
        if gen_cfg:
            payload["generation_config"] = {**gen_cfg, **payload.get("generation_config", {})}
        payload.update(_json_mode_for_provider(provider, json_mode, response_json_schema))
        return payload

    # Fallback to OpenAI style
    warnings.warn(f"Unknown provider '{provider_name}'. Defaulting to OpenAI message format.")
    msgs = [{"role": "system", "content": system_text}] if system_text else []
    msgs.extend([m for m in chat if m["role"] in ("user", "assistant")])
    return {"messages": msgs}
