# core/utils/llm/call_llm.py
# FULLY CORRECTED AND MODERNIZED
from __future__ import annotations

import json
import os
import re
import time
import traceback
import warnings
from typing import Any

import httpx

# --- EcodiaOS Core Imports ---
# This file no longer calls Synapse or Equor directly, so those imports are removed.
from .formatters import Provider, format_messages_for_provider

# --- LLM SDKs ---
try:
    from openai import APIConnectionError, AsyncOpenAI
except ImportError:
    AsyncOpenAI = None
    APIConnectionError = None
try:
    import anthropic
except ImportError:
    anthropic = None
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

# --- Configuration & Helpers ---
NETWORK_TIMEOUT = float(os.getenv("LLM_BUS_NETWORK_TIMEOUT", "10.0"))


def _try_parse_json(s: str) -> Any | None:
    """Safely extracts and parses a JSON object from a string, including from within markdown fences."""
    if not s:
        return None
    s = s.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", s, re.DOTALL)
    candidate = match.group(1) if match else s
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        try:
            start = candidate.find("{")
            end = candidate.rfind("}") + 1
            if start != -1:
                return json.loads(candidate[start:end])
        except json.JSONDecodeError:
            return None
    return None


def _get_provider_from_model_name(model_name: str) -> Provider:
    """Determines the provider (OpenAI, Anthropic, Gemini) from the model name string."""
    model_lower = model_name.lower()
    if "claude" in model_lower:
        return "anthropic"
    if "gpt" in model_lower:
        return "openai"
    if "gemini" in model_lower:
        return "gemini"
    warnings.warn(f"Could not determine provider for model '{model_name}'. Defaulting to 'openai'.")
    return "openai"


async def _call_llm_provider(
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    model_name: str,
) -> dict[str, Any]:
    """Low-level function to make a specific SDK call to an LLM provider."""
    start_time = time.monotonic()
    provider_name = _get_provider_from_model_name(model_name)
    print(f"  [Provider Call] Attempting call to '{provider_name}' with model '{model_name}'...")

    # This variable must be defined before the try block
    duration_ms = 0

    try:
        text, usage, raw_response = "", {}, {}
        provider_payload = format_messages_for_provider(provider_name, system, messages)

        # --- Nuclear Debug Logging ---
        print("\n" + "=" * 20 + f" PRE-FLIGHT CHECK: {provider_name.upper()} " + "=" * 20)

        if provider_name == "openai":
            if not AsyncOpenAI:
                raise ImportError("OpenAI SDK not installed.")

            proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
            http_client = httpx.AsyncClient(proxy=proxy_url, timeout=NETWORK_TIMEOUT * 3)
            client = AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                max_retries=1,
                http_client=http_client,
            )

            resp = await client.chat.completions.create(
                model=model_name,
                messages=provider_payload["messages"],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"} if json_mode else {"type": "text"},
            )
            text = resp.choices[0].message.content or ""
            usage = dict(resp.usage) if resp.usage else {}
            raw_response = resp.model_dump()

        elif provider_name == "anthropic":
            if not anthropic:
                raise ImportError("Anthropic SDK not installed.")
            client = anthropic.AsyncAnthropic(timeout=NETWORK_TIMEOUT * 3)
            resp = await client.messages.create(
                model=model_name,
                system=provider_payload["system"],
                messages=provider_payload["messages"],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = "".join([b.text for b in resp.content if getattr(b, "type", "") == "text"])
            usage = dict(resp.usage) if resp.usage else {}
            raw_response = resp.model_dump()

        elif provider_name == "gemini":
            if not genai or not types:
                raise ImportError("Google GenAI SDK ('google-genai') not installed.")
            client = genai.Client()

            config = types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                response_mime_type="application/json" if json_mode else "text/plain",
            )

            # The new SDK takes a system_instruction argument separately
            model = client.get_model(model_name)
            resp = await model.generate_content_async(
                contents=provider_payload["messages"],
                generation_config=config,
                system_instruction=provider_payload["system"],
            )

            text = resp.text
            usage = {}  # Not provided in the same format by this SDK
            raw_response = str(resp)

        else:
            raise ValueError(f"Provider '{provider_name}' is not supported.")

        # ======================= APPLY FIX HERE =======================
        # Calculate duration INSIDE the try block on success
        duration_ms = int((time.monotonic() - start_time) * 1000)
        # ============================================================

        print("\n" + "=" * 20 + " LLM PROVIDER SUCCESS " + "=" * 20)
        print(f"Provider: {provider_name}, Duration: {duration_ms}ms")
        print("[Raw Response Body]")
        print(json.dumps(raw_response, indent=2))
        print("=" * 64 + "\n")

        return {"ok": True, "text": text, "usage": usage, "duration_ms": duration_ms}

    except Exception as e:
        # Calculate duration inside the except block on failure
        duration_ms = int((time.monotonic() - start_time) * 1000)
        error_name = type(e).__name__

        print("\n" + "=" * 20 + " LLM PROVIDER FAILED " + "=" * 20)
        print(f"Provider: {provider_name}, Duration: {duration_ms}ms")
        print(f"Error Type: {error_name}")
        print(f"Error Details: {e}")
        print("\n[Full Traceback]")
        traceback.print_exc()
        print("=" * 61 + "\n")

        warnings.warn(
            f"LLM provider '{provider_name}' failed after {duration_ms}ms. Error: {error_name}: {e}",
        )
        return {"ok": False, "error": f"{error_name}: {e}", "duration_ms": duration_ms}


async def execute_llm_call(
    messages: list[dict[str, str]],
    policy: dict[str, Any],
    json_mode: bool = False,
    **kwargs: Any,  # <-- START CORRECTION: Accept extra keyword arguments
) -> dict[str, Any]:
    """
    The modern, simplified entrypoint for the LLM Bus. It takes a fully formed
    request and executes it based on the provided policy.
    """
    # --- ADD DEBUG LOG ---
    print(f"[LLM Executor] Received call. Ignoring extra kwargs: {kwargs.keys()}")
    # --- END CORRECTION ---

    start_time = time.monotonic()

    model_name = policy.get("model", "gemini-1.5-flash")
    temperature = policy.get("temperature", 0.5)
    max_tokens = policy.get("max_tokens", 4096)

    system_prompt = ""
    if messages and messages[0].get("role") == "system":
        system_prompt = messages[0].get("content", "")

    provider_result = await _call_llm_provider(
        messages=messages,
        system=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
        model_name=model_name,
    )

    if not provider_result.get("ok"):
        return {"error": "LLM Provider Error", "details": provider_result.get("error")}

    final_text = provider_result.get("text")
    parsed_json = _try_parse_json(final_text) if json_mode else None

    total_duration_ms = int((time.monotonic() - start_time) * 1000)

    return {
        "text": final_text,
        "json": parsed_json,
        "usage": provider_result.get("usage"),
        "policy_used": policy,
        "timing_ms": {"total": total_duration_ms, "provider": provider_result.get("duration_ms")},
    }
