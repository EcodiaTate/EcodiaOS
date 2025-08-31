# systems/common/conflict_sdk.py
from __future__ import annotations

import hashlib
import json
import os
import threading
import traceback
from typing import Any

from core.llm.bus import event_bus

_is_logging_conflict = threading.local()
_is_logging_conflict.value = False

REDACT_KEYS = {"password", "token", "authorization", "api_key", "secret", "cookie"}


def _redact(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in (d or {}).items():
        if k.lower() in REDACT_KEYS:
            out[k] = "***"
        else:
            out[k] = v if isinstance(v, int | float | bool) else str(v)[:2048]
    return out


def _normalize_stack(tb_list, depth: int = 6) -> str:
    frags = []
    for f in tb_list[-depth:]:
        frags.append(f"{f.filename.split(os.sep)[-1]}:{f.lineno}:{f.name}")
    return "|".join(frags)


def make_signature(exc: BaseException, component: str, version: str, extra: dict[str, Any]) -> str:
    tb = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    norm = {
        "etype": exc.__class__.__name__,
        "stack": _normalize_stack(tb),
        "component": component,
        "version": (version or "").split("+")[0] if version else None,  # major-ish
        "hints": sorted(
            [(k, str(extra.get(k))[:64]) for k in (extra or {}) if k in {"route", "tool", "file"}],
        ),
    }
    s = json.dumps(norm, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


async def log_conflict(
    *,
    exc: BaseException,
    component: str,
    severity: str = "medium",
    version: str | None = None,
    context: dict[str, Any] | None = None,
):
    """
    Safely logs a conflict by publishing a decoupled event.
    Includes a recursion guard to prevent feedback loops.
    """
    if getattr(_is_logging_conflict, "value", False):
        print(
            f"!!! RECURSION DETECTED in ConflictSDK. Suppressing follow-up error from '{component}'.",
        )
        return

    try:
        _is_logging_conflict.value = True

        # 1. Prepare the data payload (logic is the same as before)
        stack_blob = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        extra = _redact(context or {})
        sig = make_signature(exc, component, version or "", extra)

        conflict_payload = {
            "component": component,
            "description": str(exc)[:512],
            "severity": severity,
            "version": version or "",
            "context": extra,
            "signature": sig,
            "etype": exc.__class__.__name__,
            "stack_blob": stack_blob,
        }

        # 2. Publish the event (fire-and-forget)
        # This decouples the SDK from the database writer.
        await event_bus.publish("conflict_detected", conflict_payload)

    finally:
        # Ensure the guard is always released
        _is_logging_conflict.value = False
