"""
Tool Registration & Logging Utilities (driverless-friendly)

- Uses `_raw_add_node` to upsert/embed Tool nodes.
- Ensures meaningful `embed_text` (docstring → signature → fqn).
- Wrapper lets tools keep a `driver`-ish first param for back-compat, but never *requires* it.
- Logging can be toggled by passing driver_like in {"noop","none","disabled","off",""} → no-op.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import time
from collections.abc import Callable
from typing import Any

from core.utils.neo.cypher_query import cypher_query

# -------- driver coalescer (inline, test-friendly) --------------------------
_NOOP_TOKENS = {"noop", "none", "disabled", "off", ""}

try:
    # Optional: allow "auto" to pull a driver for legacy paths (we still log via cypher_query)
    from core.utils.neo.neo_driver import get_driver as _get_driver  # type: ignore
except Exception:
    _get_driver = None  # type: ignore


def _is_neo_driver(x: Any) -> bool:
    # Duck-typing for both neo4j.AsyncDriver and neo4j.Driver
    return hasattr(x, "session") or hasattr(x, "async_session")


def coalesce_driver(driver_like: Any) -> Any | None:
    """
    Returns a usable Neo4j driver or None.
    - real driver -> itself
    - "auto"      -> try core.utils.neo_driver.get_driver()
    - None / "noop"/"off"/random string -> None
    """
    if driver_like is None:
        return None
    if isinstance(driver_like, str):
        token = driver_like.lower().strip()
        if token in _NOOP_TOKENS:
            return None
        if token == "auto":
            if _get_driver is None:
                return None
            try:
                return _get_driver()
            except Exception:
                return None
        # Any other string => treat as no-op for safety
        return None
    return driver_like if _is_neo_driver(driver_like) else None


# ========== Universal Tool Registry ==========
TOOL_REGISTRY: dict[str, Callable] = {}


def tool(system_name: str):
    """Registers a function as a tool under the given system name."""

    def decorator(func: Callable):
        func._is_tool = True
        func._tool_system = system_name
        func._tool_name = func.__name__
        TOOL_REGISTRY[f"{system_name}.{func.__name__}"] = func
        return func

    return decorator


def get_caller_name() -> str | None:
    """Returns the name of the function that called the tool."""
    try:
        stack = inspect.stack()
        return stack[2].function if len(stack) > 2 else stack[1].function
    except Exception:
        return None


def safe_neo_value(val: Any) -> Any:
    """Converts Python values to safe Neo4j-storable values."""
    if isinstance(val, str | int | float | bool) or val is None:
        return val
    try:
        return json.dumps(val, ensure_ascii=False, default=str)
    except Exception:
        return str(val)


async def log_tool_call_to_neo(
    driver_like: Any,
    func: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
    status: str,
    caller: str,
    start: float,
    duration: float,
    is_async: bool,
):
    """
    Logs tool invocation metadata to Neo4j. Does NOT attempt to persist result as a node.
    No-ops cleanly if a valid driver is not available (per driver_like policy).
    """
    # Resolve driver or no-op (policy control). We *do not* pass this driver to cypher_query.
    driver = coalesce_driver(driver_like)
    if driver is None:
        return  # test-safe: do nothing if no driver intent

    # Import inside to avoid import cycles during boot
    from systems.synk.core.tools.neo import _raw_add_node

    def _safe_neo_value(x: Any, max_chars: int = 8000):
        """
        Convert arbitrary Python object to a Neo4j-storable value; truncate large blobs.
        """
        if x is None or isinstance(x, str | int | float | bool):
            return x
        try:
            s = json.dumps(x, ensure_ascii=False, default=str)
        except Exception:
            s = str(x)
        if len(s) > max_chars:
            s = s[:max_chars] + "...[truncated]"
        return s

    system = getattr(func, "_tool_system", "Unknown")
    tool_name = getattr(func, "__name__", "unknown_tool")
    doc = func.__doc__ or ""
    signature = str(inspect.signature(func))
    fqn = f"{system}.{tool_name}"

    # Choose good embedding text
    embed_text = (doc.strip() or f"{tool_name} {signature}" or fqn).strip()

    # Ensure Tool node exists (and has vector)
    await _raw_add_node(
        labels=["Tool", system],
        properties={
            "name": tool_name,
            "system": system,
            "doc": doc,
            "signature": signature,
            "fqn": fqn,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        },
        embed_text=embed_text,
        force_embed=True,
    )

    call_props = {
        "system": system,
        "tool_name": tool_name,
        "args": _safe_neo_value(args),
        "kwargs": _safe_neo_value(kwargs),
        "result": _safe_neo_value(result),  # may be None if log_return=False
        "status": status,
        "caller": caller,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start)),
        "duration_sec": duration,
        "is_async": bool(is_async),
    }

    # Use SET += for parameterized property maps (CREATE (... $props) is invalid Cypher)
    tool_call_query = """
    CREATE (c:ToolCall)
    SET c += $props
    WITH c
    MATCH (t:Tool {name: $tool_name, system: $system})
    MERGE (c)-[:CALLED_TOOL]->(t)
    """
    await cypher_query(
        tool_call_query,
        {
            "props": call_props,
            "tool_name": tool_name,
            "system": system,
        },
    )


def tool_wrapper(system_name: str, *, log_return: bool = True):
    """
    Wraps tools with Neo4j logging.
    First argument may be:
      - a real Neo driver (async or sync)
      - "auto" to pull from core.utils.neo.neo_driver.get_driver()
      - "noop"/None/random string to skip logging (no-op)
    Set log_return=False to avoid logging the tool's return payload.
    """

    def decorator(func: Callable):
        async def _log_and_call(
            driver_like: Any,
            call_args: tuple[Any, ...],
            call_kwargs: dict[str, Any],
            is_async: bool,
        ):
            start = time.time()
            caller = get_caller_name() or "unknown"
            status = "success"
            result: Any = None
            caught_exc: BaseException | None = None
            try:
                # Pass the original driver_like through to preserve signature/back-compat.
                if is_async:
                    result = await func(driver_like, *call_args, **call_kwargs)
                else:
                    result = func(driver_like, *call_args, **call_kwargs)
            except BaseException as e:
                caught_exc = e
                result = repr(e)
                status = "error"

            duration = round(time.time() - start, 4)
            safe_result = result if log_return else None

            # Fire-and-forget logging (await to keep order; it’s quick)
            await log_tool_call_to_neo(
                driver_like,
                func,
                call_args,
                call_kwargs,
                safe_result,
                status,
                caller,
                start,
                duration,
                is_async=is_async,
            )

            if caught_exc is not None:
                raise caught_exc
            return result

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Accept missing/None driver-like gracefully
                driver_like = args[0] if args else None
                return await _log_and_call(
                    driver_like,
                    tuple(args[1:]) if len(args) > 1 else tuple(),
                    kwargs,
                    is_async=True,
                )

            wrapped = async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                driver_like = args[0] if args else None
                return asyncio.run(
                    _log_and_call(
                        driver_like,
                        tuple(args[1:]) if len(args) > 1 else tuple(),
                        kwargs,
                        is_async=False,
                    ),
                )

            wrapped = sync_wrapper

        return tool(system_name)(wrapped)

    return decorator
