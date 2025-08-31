# core/llm/gemini_cache.py
from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Any

# Soft import google-genai
try:
    from google import genai
    from google.genai import types as genai_types

    _HAS_GOOGLE = True
except Exception:
    genai = None  # type: ignore
    genai_types = None  # type: ignore
    _HAS_GOOGLE = False

# Central orchestrator (PromptSpec-native)
from core.prompting.orchestrator import PolicyHint, build_prompt


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


# Sensible default scopes per agent (overrideable via task["scope"])
_AGENT_DEFAULT_SCOPE: dict[str, str] = {
    "Simula": "simula.react.step",
    "Atune": "atune.schema.naming",
    "Synapse": "synapse.genesis_tool_specification",
    "Unity": "unity.deliberation.turn",
}


def _extract_system_instruction(messages: list[dict[str, Any]]) -> str:
    """
    Pull the first 'system' message content; fall back to empty string.
    """
    for m in messages:
        if m.get("role") == "system":
            c = m.get("content") or ""
            return c if isinstance(c, str) else ""
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Explicit cache APIs
# ──────────────────────────────────────────────────────────────────────────────


async def create_cache(
    *,
    model: str,
    system_instruction: str | None = None,
    contents: list[Any] | None = None,  # file refs from client.files.upload(...) allowed
    ttl_seconds: int = 3600,
    display_name: str | None = None,
) -> str:
    """
    Create a Gemini CachedContent entry and return its name.
    Use with llm_bus(..., gemini_cached_content=<name>).
    """
    _require(_HAS_GOOGLE, "google-genai package not available")
    client = genai.Client()

    cfg = genai_types.CreateCachedContentConfig(  # type: ignore
        display_name=display_name or f"cache-{_dt.datetime.now(_dt.UTC).isoformat()}",
        system_instruction=system_instruction or "",
        contents=contents or [],
        ttl=f"{int(ttl_seconds)}s",
    )

    def _call():
        cache = client.caches.create(model=model, config=cfg)
        return cache.name

    return await asyncio.to_thread(_call)


async def update_cache_ttl(*, name: str, ttl_seconds: int):
    _require(_HAS_GOOGLE, "google-genai package not available")
    client = genai.Client()
    cfg = genai_types.UpdateCachedContentConfig(ttl=f"{int(ttl_seconds)}s")  # type: ignore
    return await asyncio.to_thread(lambda: client.caches.update(name=name, config=cfg))


async def set_cache_expiry(*, name: str, expire_time: _dt.datetime):
    """expire_time must be timezone-aware (UTC recommended)."""
    _require(_HAS_GOOGLE, "google-genai package not available")
    if expire_time.tzinfo is None or expire_time.tzinfo.utcoffset(expire_time) is None:
        raise ValueError("expire_time must be timezone-aware")
    client = genai.Client()
    cfg = genai_types.UpdateCachedContentConfig(expire_time=expire_time)  # type: ignore
    return await asyncio.to_thread(lambda: client.caches.update(name=name, config=cfg))


async def delete_cache(*, name: str):
    _require(_HAS_GOOGLE, "google-genai package not available")
    client = genai.Client()
    return await asyncio.to_thread(lambda: client.caches.delete(name))


async def list_caches() -> list[Any]:
    _require(_HAS_GOOGLE, "google-genai package not available")
    client = genai.Client()
    return await asyncio.to_thread(lambda: list(client.caches.list()))


# ──────────────────────────────────────────────────────────────────────────────
# PromptSpec-native helpers
# ──────────────────────────────────────────────────────────────────────────────


async def create_spec_prompt_cache(
    *,
    scope: str,
    model: str = "gemini-2.5-flash",
    ttl_seconds: int = 3600,
    display_name: str | None = None,
    summary: str | None = None,
    context: dict[str, Any] | None = None,
    extra_contents: list[Any] | None = None,
) -> str:
    """
    Build a PromptSpec-scoped prompt, extract the system preamble, and cache it in Gemini.
    Returns cache.name.
    """
    _require(_HAS_GOOGLE, "google-genai package not available")

    hint = PolicyHint(
        scope=scope,
        summary=summary or f"System cache seed for scope {scope}",
        context=context or {},
    )
    o = await build_prompt(hint)
    system_instruction = _extract_system_instruction(o.messages)

    return await create_cache(
        model=model,
        system_instruction=system_instruction,
        contents=extra_contents or [],
        ttl_seconds=ttl_seconds,
        display_name=display_name or f"{scope}:{model}",
    )


async def create_agent_prompt_cache(
    *,
    agent_name: str,
    model: str = "gemini-2.5-flash",
    slot: str = "system",
    task: dict[str, Any] | None = None,  # may include {"scope": "...", ...}
    ttl_seconds: int = 3600,
    display_name: str | None = None,
    extra_contents: list[Any] | None = None,
) -> str:
    """
    Resolve the agent's system prompt via the central orchestrator (PromptSpec),
    then create a Gemini cache from it. Returns cache.name.

    You can override which PromptSpec to use by passing task={"scope": "<your.scope.id>"}.
    """
    _require(_HAS_GOOGLE, "google-genai package not available")

    task = task or {}
    scope = task.get("scope") or _AGENT_DEFAULT_SCOPE.get(agent_name, "simula.react.step")

    ctx = {
        # free-form vars the spec/template may use:
        "vars": {
            "agent_name": agent_name,
            "slot": slot,
            **{k: v for k, v in task.items() if k != "scope"},
        },
    }

    return await create_spec_prompt_cache(
        scope=scope,
        model=model,
        ttl_seconds=ttl_seconds,
        display_name=display_name or f"{agent_name}:{slot}:{model}",
        summary=f"System cache for {agent_name} ({slot})",
        context=ctx,
        extra_contents=extra_contents,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Batch fan-out helper (kept lightweight)
# ──────────────────────────────────────────────────────────────────────────────


async def fanout_generate_content(jobs: list[dict[str, Any]], *, concurrency: int = 8) -> list[Any]:
    """
    Simple concurrency-limited fan-out for many generate_content calls.
    Each job must be a dict suitable for client.models.generate_content(**job).
    Tip: Pre-fill 'cached_content' in each job to leverage 50% cache pricing.
    """
    _require(_HAS_GOOGLE, "google-genai package not available")
    client = genai.Client()
    sem = asyncio.Semaphore(concurrency)

    async def _one(job: dict[str, Any]) -> Any:
        async with sem:

            def _call():
                return client.models.generate_content(**job)

            return await asyncio.to_thread(_call)

    return await asyncio.gather(*(_one(j) for j in jobs))
