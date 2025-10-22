# systems/qora/core/immune/conflict_sdk.py
from __future__ import annotations

import hashlib
import inspect
import json
import os
import time as _time
import traceback
from collections import OrderedDict
from contextlib import nullcontext
from contextvars import ContextVar
from typing import Any

from core.llm.bus import event_bus

__all__ = ["log_conflict"]


# -----------------------------------------------------------------------------
# Immune-section wrapper (supports 0-arg or 1-arg, sync or async context manager)
# -----------------------------------------------------------------------------
def _get_immune_cm(tag: str = ""):
    try:
        from systems.qora.core.immune.auto_instrument import immune_section as _immune

        try:
            return _immune(tag)  # prefer 1-arg
        except TypeError:
            return _immune()  # fallback: 0-arg
    except Exception:
        return nullcontext()  # no-op if immune stack unavailable


def _is_async_cm(cm) -> bool:
    aenter = getattr(cm, "__aenter__", None)
    aexit = getattr(cm, "__aexit__", None)
    return inspect.iscoroutinefunction(aenter) or inspect.iscoroutinefunction(aexit)


# -----------------------------------------------------------------------------
# Recursion guard + per-component TTL throttle for recursion warnings
# -----------------------------------------------------------------------------
_IN_CONFLICT: ContextVar[bool] = ContextVar("_IN_CONFLICT", default=False)

# Backwards-compat: if older env var is set, use it; otherwise use *_TTL_* one.
_RECURSION_TTL_SEC = float(
    os.getenv("CONFLICTSDK_RECURSION_TTL_SEC")
    or os.getenv("CONFLICTSDK_RECURSION_LOG_PERIOD_SEC", "5.0"),
)
_RECURSION_KEYS_MAX = int(os.getenv("CONFLICTSDK_RECURSION_KEYS_MAX", "512"))
_LAST_RECURSION_BY_COMP: OrderedDict[str, float] = OrderedDict()


def _record_recursion(component: str) -> bool:
    """
    Returns True if we should log a recursion warning for this component now,
    else False if suppressed by TTL (process-wide, per-component).
    """
    now = _time.time()
    last = _LAST_RECURSION_BY_COMP.get(component)
    if last is not None and (now - last) < _RECURSION_TTL_SEC:
        return False
    if component in _LAST_RECURSION_BY_COMP:
        _LAST_RECURSION_BY_COMP.move_to_end(component, last=True)
    _LAST_RECURSION_BY_COMP[component] = now
    while len(_LAST_RECURSION_BY_COMP) > _RECURSION_KEYS_MAX:
        _LAST_RECURSION_BY_COMP.popitem(last=False)
    return True


# -----------------------------------------------------------------------------
# Publish de-dup (don’t emit the same signature too often)
# -----------------------------------------------------------------------------
_EMIT_TTL_SEC = float(os.getenv("CONFLICTSDK_EMIT_TTL_SEC", "60"))  # 60s default
_EMIT_CACHE_MAX = int(os.getenv("CONFLICTSDK_EMIT_CACHE_MAX", "2048"))
_LAST_EMIT_BY_SIG: OrderedDict[str, float] = OrderedDict()


def _record_emit(sig: str) -> bool:
    """Return True if we should emit now; False if suppressed by TTL."""
    now = _time.time()
    last = _LAST_EMIT_BY_SIG.get(sig)
    if last is not None and (now - last) < _EMIT_TTL_SEC:
        return False
    if sig in _LAST_EMIT_BY_SIG:
        _LAST_EMIT_BY_SIG.move_to_end(sig, last=True)
    _LAST_EMIT_BY_SIG[sig] = now
    while len(_LAST_EMIT_BY_SIG) > _EMIT_CACHE_MAX:
        _LAST_EMIT_BY_SIG.popitem(last=False)
    return True


# -----------------------------------------------------------------------------
# Redaction / signature helpers
# -----------------------------------------------------------------------------
REDACT_KEYS = {
    "password",
    "token",
    "authorization",
    "api_key",
    "secret",
    "cookie",
    "authorization_bearer",
}


def _redact(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (d or {}).items():
        if str(k).lower() in REDACT_KEYS:
            out[k] = "***"
        else:
            if isinstance(v, (int, float, bool)) or v is None:
                out[k] = v
            else:
                try:
                    s = json.dumps(v, ensure_ascii=False)
                except Exception:
                    s = str(v)
                out[k] = s[:2048]
    return out


def _normalize_stack(tb_list, depth: int = 6) -> str:
    frags = []
    for f in tb_list[-depth:]:
        frags.append(f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}")
    return "|".join(frags)


def make_signature(exc: BaseException, component: str, version: str, extra: dict[str, Any]) -> str:
    tb = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    norm = {
        "etype": exc.__class__.__name__,
        "stack": _normalize_stack(tb),
        "component": component,
        "version": (version or "").split("+")[0] if version else None,
        # keep only a few stable hints; bound & shortened
        "hints": sorted(
            (k, str(extra.get(k))[:64]) for k in ("route", "tool", "file") if k in (extra or {})
        ),
    }
    s = json.dumps(norm, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
# Separate throttle for printing publish failures (task-local, backwards compat)
_LAST_PUBLISH_ERR_LOG = ContextVar("_LAST_PUBLISH_ERR_LOG", default=0.0)
_PUBLISH_ERR_TTL_SEC = float(os.getenv("CONFLICTSDK_PUBLISH_ERR_TTL_SEC", "2.0"))


async def log_conflict(
    *,
    exc: BaseException,
    component: str,
    severity: str = "medium",
    version: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """
    Publish a conflict event (deduped by signature over a TTL).
    The whole publish path is wrapped in `immune_section` (sync or async).
    Re-entrancy (recursive calls from the immune path) is detected and
    per-component throttled to prevent log storms.

    Environment knobs:
      CONFLICTSDK_RECURSION_TTL_SEC          (float, default 5.0)
      CONFLICTSDK_RECURSION_KEYS_MAX         (int, default 512)
      CONFLICTSDK_EMIT_TTL_SEC               (float, default 60.0)
      CONFLICTSDK_EMIT_CACHE_MAX             (int, default 2048)
      CONFLICTSDK_PUBLISH_ERR_TTL_SEC        (float, default 2.0)
    """
    comp = component or "unknown"

    # Recursion guard: if we're already in conflict logging, only print (throttled) once in a while
    if _IN_CONFLICT.get():
        if _record_recursion(comp):
            print(
                f"!!! RECURSION DETECTED in ConflictSDK. Suppressing follow-up error from '{comp}'.",
            )
        return

    token = _IN_CONFLICT.set(True)
    try:
        stack_blob = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        extra = _redact(context or {})
        sig = make_signature(exc, comp, version or "", extra)

        # Suppress duplicate emits for same signature within TTL window
        if not _record_emit(sig):
            return

        payload = {
            "component": comp,
            "description": str(exc)[:512],
            "severity": str(severity or "medium").lower(),
            "version": version or "",
            "context": extra,
            "signature": sig,
            "etype": exc.__class__.__name__,
            "stack_blob": stack_blob,
            "source_system": "qora",
        }

        cm = _get_immune_cm("conflict_sdk.publish")
        if _is_async_cm(cm):
            async with cm:  # type: ignore[misc]
                await event_bus.publish("conflict_detected", payload)
        else:
            with cm:
                await event_bus.publish("conflict_detected", payload)

    except Exception as pub_err:
        now = _time.time()
        last = _LAST_PUBLISH_ERR_LOG.get()
        if now - last >= _PUBLISH_ERR_TTL_SEC:
            print(
                f"!!! ConflictSDK: failed to publish conflict ({type(pub_err).__name__}): {pub_err}",
            )
            _LAST_PUBLISH_ERR_LOG.set(now)
    finally:
        _IN_CONFLICT.reset(token)
