# systems/unity/core/cognition/llm_util.py
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from core.llm.bus import event_bus


async def llm_call(
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = False,
    headers: dict[str, str] | None = None,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    call_id = str(uuid.uuid4())
    response_event = f"llm_call_response:{call_id}"
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    def on_response(resp: dict):
        if not fut.done():
            fut.set_result(resp)

    event_bus.subscribe(response_event, on_response)

    llm_payload = {
        "provider_overrides": {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    extra_headers = {
        "x-budget-ms": "45000",
        "x-spec-id": "unity.cognition.v2",
        "x-spec-version": "v1",
    }
    if headers:
        extra_headers.update(headers)
    
    # --- FIX ---
    # The keyword 'event_type=' has been removed.
    await event_bus.publish(
        "llm_call_request",
        call_id=call_id,
        llm_payload=llm_payload,
        extra_headers=extra_headers,
    )

    resp = await asyncio.wait_for(fut, timeout=timeout_s)
    # unify a tiny shape
    return {
        "text": (resp.get("text") or resp.get("content") or "").strip(),
        "json": resp.get("json"),
        "raw": resp,
    }