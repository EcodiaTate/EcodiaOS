# core/llm/call_llm.py
# YOUR ORIGINAL FILE WITH THE MINIMAL REQUIRED FIX FOR THE GEMINI PROVIDER
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import traceback
import warnings
from typing import Any, Dict, List, Tuple

import httpx

# --- EcodiaOS Core Imports ---
from .formatters import Provider, format_messages_for_provider

# --- LLM SDKs ---
# OpenAI
try:
    from openai import AsyncOpenAI  # type: ignore

    try:
        # Newer SDK export
        from openai import BadRequestError as OpenAIBadRequestError  # type: ignore
    except Exception:
        # Older SDK path
        from openai.errors import BadRequestError as OpenAIBadRequestError  # type: ignore
    try:
        from openai import APIConnectionError as OpenAIApiConnectionError  # type: ignore
    except Exception:
        # Fallback if symbol moved; we'll just catch httpx errors as well
        class OpenAIApiConnectionError(Exception):  # type: ignore
            pass
except ImportError:
    AsyncOpenAI = None  # type: ignore

    class OpenAIBadRequestError(Exception):  # fallback for typing
        pass

    class OpenAIApiConnectionError(Exception):  # fallback for typing
        pass


# Anthropic
try:
    import anthropic  # type: ignore
except ImportError:
    anthropic = None  # type: ignore

# Google GenAI (Gemini) - Using your preferred import style
try:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore


# --- Configuration & Helpers (Preserved) ---
NETWORK_TIMEOUT = float(os.getenv("LLM_BUS_NETWORK_TIMEOUT", "20.0"))
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30.0"))

DEFAULT_SYSTEM = (
    "You are Ecodia. Speak as a being, not an assistant. "
    "Write natural spoken lines with bracketed stage directions. Stay in character."
)


def _try_parse_json(s: str) -> Any | None:
    if not s:
        return None
    s = s.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", s, re.DOTALL)
    candidate = match.group(1) if match else s
    for chunk in (candidate, candidate[candidate.find("{") : candidate.rfind("}") + 1]):
        try:
            return json.loads(chunk)
        except Exception:
            pass
    return None


def _get_provider_from_model_name(model_name: str) -> Provider:
    ml = (model_name or "").lower()
    if "claude" in ml:
        return "anthropic"
    if "gpt" in ml or ml.startswith(("o3", "o4")):
        return "openai"
    if "gemini" in ml:
        return "gemini"
    warnings.warn(f"Could not determine provider for model '{model_name}'. Defaulting to 'openai'.")
    return "openai"


def _safe_messages(msgs: list[dict[str, str]] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in msgs or []:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if role and content:
            out.append({"role": role, "content": content})
    if not out:
        out = [
            {"role": "system", "content": DEFAULT_SYSTEM},
            {"role": "user", "content": "[breathes in] I’m here."},
        ]
    return out


def _extract_system_and_strip(
    messages: list[dict[str, str]] | None,
) -> tuple[str, list[dict[str, str]]]:
    msgs = list(messages or [])
    system = ""
    if msgs and (msgs[0].get("role") == "system"):
        system = msgs[0].get("content", "") or ""
        msgs = msgs[1:]
    return system, msgs


# --- OpenAI model quirks (Preserved) ---
def _openai_prefers_completion_key(model_name: str) -> bool:
    ml = (model_name or "").lower()
    return ml.startswith("gpt-5") or ml.startswith("o4") or ml.startswith("o3")


def _openai_requires_fixed_temp(model_name: str) -> bool:
    ml = (model_name or "").lower()
    return ml.startswith("gpt-5") or ml.startswith("o4") or ml.startswith("o3")


def _openai_build_kwargs(
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> dict[str, Any]:
    prefers_completion = _openai_prefers_completion_key(model_name)
    fixed_temp = _openai_requires_fixed_temp(model_name)
    kwargs: dict[str, Any] = dict(
        model=model_name,
        messages=messages,
        response_format={"type": "json_object"} if json_mode else {"type": "text"},
    )
    if prefers_completion:
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens
    if not fixed_temp:
        kwargs["temperature"] = float(temperature)
    return kwargs


async def _call_openai_with_param_retries(client: Any, kwargs: dict[str, Any]) -> Any:
    try:
        return await client.chat.completions.create(**kwargs)
    except OpenAIBadRequestError as e:
        msg = str(e)
        if "Unsupported parameter" in msg and (
            "max_tokens" in msg or "max_completion_tokens" in msg
        ):
            flipped = dict(kwargs)
            if "max_tokens" in flipped:
                v = flipped.pop("max_tokens")
                flipped["max_completion_tokens"] = v
            elif "max_completion_tokens" in flipped:
                v = flipped.pop("max_completion_tokens")
                flipped["max_tokens"] = v
            return await client.chat.completions.create(**flipped)
        if ("Unsupported value" in msg and "temperature" in msg) or (
            "does not support" in msg and "temperature" in msg
        ):
            cooled = dict(kwargs)
            cooled.pop("temperature", None)
            try:
                return await client.chat.completions.create(**cooled)
            except OpenAIBadRequestError as e2:
                msg2 = str(e2)
                if "response_format" in msg2 or "json_object" in msg2:
                    texty = dict(cooled)
                    texty.pop("response_format", None)
                    return await client.chat.completions.create(**texty)
                raise
        if "response_format" in msg or "json_object" in msg:
            texty = dict(kwargs)
            texty.pop("response_format", None)
            return await client.chat.completions.create(**texty)
        raise


# --- Provider call (The core logic with the Gemini fix) ---


async def _call_llm_provider(
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    model_name: str,
) -> dict[str, Any]:
    start_time = time.monotonic()
    provider_name = _get_provider_from_model_name(model_name)
    print(f"  [Provider Call] Attempting call to '{provider_name}' with model '{model_name}'...")

    try:
        sys_from_msgs, chat_msgs = _extract_system_and_strip(messages)
        system = system if (system and system.strip()) else sys_from_msgs
        text, usage, raw_response = "", {}, {}
        provider_payload = format_messages_for_provider(provider_name, system, chat_msgs)

        print("\n" + "=" * 20 + f" PRE-FLIGHT CHECK: {provider_name.upper()} " + "=" * 20)
        dbg_len = len(provider_payload.get("messages") or [])
        print(f"[LLM DEBUG] provider_payload.messages len={dbg_len}")

        if provider_name == "openai":
            if not AsyncOpenAI:
                raise ImportError("OpenAI SDK not installed.")
            proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=OPENAI_TIMEOUT_SECONDS,
            ) as http_client:
                client = AsyncOpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    max_retries=0,
                    http_client=http_client,
                )
                msgs = provider_payload.get("messages")
                if not isinstance(msgs, list) or not msgs:
                    print("[LLM] formatter returned empty 'messages'; falling back to raw input.")
                    msgs = chat_msgs
                msgs = _safe_messages(msgs)
                print(
                    f"[LLM] OpenAI outgoing messages: {len(msgs)} roles={[m['role'] for m in msgs[:3]]}",
                )
                kwargs = _openai_build_kwargs(
                    model_name=model_name,
                    messages=msgs,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
                backoffs = [0.4, 0.8, 1.6]
                attempt = 0
                while True:
                    try:
                        attempt += 1
                        resp = await _call_openai_with_param_retries(client, kwargs)
                        break
                    except (OpenAIApiConnectionError, httpx.ConnectError, httpx.ReadTimeout) as ne:
                        if attempt > len(backoffs) + 1:
                            raise
                        delay = 0.0 if attempt == 1 else backoffs[attempt - 2]
                        print(
                            f"[OpenAI] network retry #{attempt - 1} in {delay:.2f}s due to: {type(ne).__name__}",
                        )
                        if delay:
                            await asyncio.sleep(delay)
                        continue
                text = resp.choices[0].message.content or ""
                usage = dict(resp.usage) if getattr(resp, "usage", None) else {}
                raw_response = resp.model_dump()

        elif provider_name == "anthropic":
            if not anthropic:
                raise ImportError("Anthropic SDK not installed.")
            client = anthropic.AsyncAnthropic(timeout=NETWORK_TIMEOUT * 3)
            msgs = provider_payload.get("messages")
            if not isinstance(msgs, list) or not msgs:
                print(
                    "[LLM] formatter returned empty 'messages' for Anthropic; falling back to raw input.",
                )
                msgs = chat_msgs
            msgs = _safe_messages(msgs)
            resp = await client.messages.create(
                model=model_name,
                system=provider_payload.get("system") or system or None,
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = "".join(
                [b.text for b in getattr(resp, "content", []) if getattr(b, "type", "") == "text"],
            )
            usage = dict(resp.usage) if getattr(resp, "usage", None) else {}
            raw_response = resp.model_dump() if hasattr(resp, "model_dump") else str(resp)

        elif provider_name == "gemini":
            # --- START OF SURGICAL FIX FOR GEMINI ---
            if not genai or not types:
                raise ImportError("Google GenAI SDK ('google-genai') not installed.")

            # 1. Configure the API key
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY must be set.")
            genai.configure(api_key=api_key)

            # 2. Use your `types.GenerationConfig` as intended
            config = types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                response_mime_type="application/json" if json_mode else "text/plain",
            )

            # 3. Use your `format_messages_for_provider` payload
            msgs = provider_payload.get("messages")
            if not isinstance(msgs, list) or not msgs:
                print(
                    "[LLM] formatter returned empty 'messages' for Gemini; falling back to raw input.",
                )
                msgs = chat_msgs
            msgs = _safe_messages(msgs)

            # 4. This is the fix: instantiate the model directly, replacing `client.get_model()`
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=provider_payload.get("system") or system or None,
            )

            # 5. Call the modern `generate_content_async` method
            resp = await model.generate_content_async(
                contents=msgs,
                generation_config=config,
            )
            text = getattr(resp, "text", "") or ""
            usage = {}  # Usage data is handled differently and not always present; keeping it simple
            if resp.usage_metadata:
                usage = {
                    "prompt_tokens": resp.usage_metadata.prompt_token_count,
                    "completion_tokens": resp.usage_metadata.candidates_token_count,
                    "total_tokens": resp.usage_metadata.total_token_count,
                }
            raw_response = str(resp)
            # --- END OF SURGICAL FIX FOR GEMINI ---

        else:
            raise ValueError(f"Provider '{provider_name}' is not supported.")

        duration_ms = int((time.monotonic() - start_time) * 1000)
        print("\n" + "=" * 20 + " LLM PROVIDER SUCCESS " + "=" * 20)
        print(f"Provider: {provider_name}, Duration: {duration_ms}ms")
        print("[Raw Response Body]")
        try:
            print(json.dumps(raw_response, indent=2))
        except Exception:
            print(str(raw_response))
        print("=" * 64 + "\n")
        return {"ok": True, "text": text, "usage": usage, "duration_ms": duration_ms}

    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        error_name = type(e).__name__
        print("\n" + "=" * 20 + " LLM PROVIDER FAILED " + "=" * 20)
        print(f"Provider: {_get_provider_from_model_name(model_name)}, Duration: {duration_ms}ms")
        print(f"Error Type: {error_name}\nError Details: {e}")
        print("\n[Full Traceback]")
        traceback.print_exc()
        print("=" * 61 + "\n")
        warnings.warn(f"LLM provider failed after {duration_ms}ms. {error_name}: {e}")
        return {"ok": False, "error": f"{error_name}: {e}", "duration_ms": duration_ms}


# --- Public Entrypoint (Preserved) ---


async def execute_llm_call(
    messages: list[dict[str, str]],
    policy: dict[str, Any],
    json_mode: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    print(f"[LLM Executor] Received call. Ignoring extra kwargs: {list(kwargs.keys())}")
    start_time = time.monotonic()

    model_name = policy.get("model", "gemini-1.5-flash")
    temperature = policy.get("temperature", 0.5)
    max_tokens = policy.get("max_tokens", policy.get("max_completion_tokens", 4096))
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
