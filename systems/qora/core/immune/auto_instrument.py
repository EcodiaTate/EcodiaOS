# systems/qora/core/immune/auto_instrument.py
# DESCRIPTION: Hardened version with detailed comments explaining the resiliency patterns.

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import pkgutil
import sys
import threading
from collections.abc import Callable, Sequence
from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar
from types import ModuleType

from systems.qora.core.immune.conflict_sdk import log_conflict

# A flag to prevent re-wrapping a function that has already been instrumented.
IMMUNE_FLAG = "__immune_wrapped__"

# This ContextVar is the cornerstone of recursion safety. When True, all immune
# wrappers will suppress conflict logging, preventing loops where the logging
# or escalation process itself fails and creates a new conflict. 
_IMMUNE_ACTIVE: ContextVar[bool] = ContextVar("immune_active", default=False)


@asynccontextmanager
async def immune_section():
    """
    An async context manager to globally suppress conflict logging in a code block.
    Crucial for wrapping sensitive operations like conflict escalation.
    """
    token = _IMMUNE_ACTIVE.set(True)
    try:
        yield
    finally:
        _IMMUNE_ACTIVE.reset(token)


@contextmanager
def immune_section_sync():
    """A synchronous context manager to globally suppress conflict logging."""
    token = _IMMUNE_ACTIVE.set(True)
    try:
        yield
    finally:
        _IMMUNE_ACTIVE.reset(token)


def _wrap_callable(fn, *, component: str, version: str | None, severity: str = "medium"):
    """Wraps a callable to report exceptions, unless in an immune section."""
    if getattr(fn, IMMUNE_FLAG, False):
        return fn # Already wrapped

    context_payload = {
        "func": getattr(fn, "__qualname__", fn.__name__),
        "module": getattr(fn, "__module__", component),
        "severity": severity,
    }

    if inspect.iscoroutinefunction(fn):
        async def wrapped(*a, **kw):
            try:
                return await fn(*a, **kw)
            except Exception as e:
                # THE GUARD: If _IMMUNE_ACTIVE is true, we are inside a sensitive
                # operation. We must not log a new conflict. Re-raise immediately. 
                if _IMMUNE_ACTIVE.get():
                    raise
                await log_conflict(exc=e, component=component, version=version, context=context_payload)
                raise
    else:
        def wrapped(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as e:
                # THE GUARD (SYNC): Same principle as the async version.
                if _IMMUNE_ACTIVE.get():
                    raise
                try:
                    # Best-effort fire-and-forget logging for sync contexts.
                    loop = asyncio.get_running_loop()
                    loop.create_task(log_conflict(exc=e, component=component, version=version, context=context_payload))
                except RuntimeError: # No running loop
                    asyncio.run(log_conflict(exc=e, component=component, version=version, context=context_payload))
                raise

    # Preserve original function metadata for introspection.
    for attr in ("__name__", "__qualname__", "__doc__"):
        setattr(wrapped, attr, getattr(fn, attr, None))
    setattr(wrapped, IMMUNE_FLAG, True)
    return wrapped


def _instrument_module(mod: ModuleType, *, component: str, version: str | None, include_privates: bool):
    for name, obj in list(vars(mod).items()):
        if not include_privates and name.startswith("_"):
            continue
        try:
            if inspect.isfunction(obj) and getattr(obj, "__module__", None) == mod.__name__:
                setattr(mod, name, _wrap_callable(obj, component=component, version=version))
            elif inspect.isclass(obj):
                for item_name, attr in list(obj.__dict__.items()):
                    if not include_privates and item_name.startswith("_"):
                        continue
                    
                    fn_to_wrap = None
                    if isinstance(attr, staticmethod):
                        fn_to_wrap = attr.__func__
                        wrapped = _wrap_callable(fn_to_wrap, component=component, version=version)
                        setattr(obj, item_name, staticmethod(wrapped))
                    elif isinstance(attr, classmethod):
                        fn_to_wrap = attr.__func__
                        wrapped = _wrap_callable(fn_to_wrap, component=component, version=version)
                        setattr(obj, item_name, classmethod(wrapped))
                    elif inspect.isfunction(attr):
                        fn_to_wrap = attr
                        wrapped = _wrap_callable(fn_to_wrap, component=component, version=version)
                        setattr(obj, item_name, wrapped)
        except Exception:
            continue # Instrumenting is best-effort


async def install_immune(
    include_packages: Sequence[str] = ("systems", "core", "services"),
    *,
    version: str | None = None,
    include_privates: bool = False,
    exclude_predicate: Callable[[str], bool] | None = None,
    component_resolver: Callable[[str], str] | None = None,
):
    """
    Auto-wraps callables in specified packages and sets global exception hooks.
    Call once at application startup.
    """
    exclude_predicate = exclude_predicate or (lambda name: False)
    component_resolver = component_resolver or (lambda modname: modname.split(".")[0])

    # Instrument already-loaded and future-loaded modules
    packages_to_scan = [pkg for pkg in include_packages if pkg in sys.modules]
    for pkg_name in packages_to_scan:
        base = importlib.import_module(pkg_name)
        for _, name, _ in pkgutil.walk_packages(base.__path__, prefix=pkg_name + "."):
            if exclude_predicate(name):
                continue
            try:
                mod = importlib.import_module(name)
                _instrument_module(mod, component=component_resolver(name), version=version, include_privates=include_privates)
            except Exception:
                continue

    # Set global hooks to catch any unhandled exceptions at the process boundaries.
    # These also respect the _IMMUNE_ACTIVE guard.
    old_excepthook = sys.excepthook
    def excepthook(etype, value, tb):
        if not _IMMUNE_ACTIVE.get():
            asyncio.run(log_conflict(exc=value, component="global", version=version, context={"where": "sys.excepthook"}))
        old_excepthook(etype, value, tb)
    sys.excepthook = excepthook

    old_thread_hook = threading.excepthook
    def thread_hook(args: threading.ExceptHookArgs):
        if not _IMMUNE_ACTIVE.get():
            asyncio.run(log_conflict(exc=args.exc_value, component="thread", version=version, context={"thread": str(args.thread)}))
        old_thread_hook(args)
    threading.excepthook = thread_hook