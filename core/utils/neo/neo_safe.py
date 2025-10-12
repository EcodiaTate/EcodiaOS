# core/utils/neo_safe.py
from __future__ import annotations

import warnings
from typing import Any

__all__ = ["coalesce_driver", "_is_neo_driver"]

_DEPRECATION_MSG = (
    "[neo_safe] Driver objects are deprecated. "
    "All graph I/O must go through core.utils.neo.cypher_query(...) "
    "(driverless). 'auto' resolution has been removed and will return None."
)

# core/utils/neo/props.py
from __future__ import annotations

import json
from typing import Any

_PRIMS = (str, int, float, bool, type(None))


def _is_prim(x: Any) -> bool:
    return isinstance(x, _PRIMS)


def _safe_leaf(x: Any) -> Any:
    # numpy → list
    try:
        import numpy as np  # type: ignore

        if isinstance(x, np.ndarray):
            x = x.tolist()
    except Exception:
        pass
    # primitives
    if _is_prim(x):
        return x
    # list/tuple
    if isinstance(x, (list, tuple)):
        # if any element is non-primitive → JSON
        if any(not _is_prim(e) for e in x):
            return json.dumps(x, ensure_ascii=False)
        return list(x)
    # dict/other complex → JSON
    if isinstance(x, dict):
        # keep as JSON string (Neo4j props can’t be maps)
        return json.dumps(x, ensure_ascii=False)
    return json.dumps(x, ensure_ascii=False)


def neo_safe_map(d: dict[str, Any]) -> dict[str, Any]:
    """
    Make a *property map* safe: preserve top-level keys, but
    convert any non-primitive *values* (incl nested dicts/lists of dicts) to JSON strings.
    """
    return {k: _safe_leaf(v) for k, v in d.items()}


def neo_safe_params(params: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize *all* params conservatively:
    - If a param looks like a property map ('props' or endswith '_props'), make it a safe map.
    - Otherwise, primitive stays; dicts/lists-of-dicts become JSON.
    """
    out: dict[str, Any] = {}
    for k, v in (params or {}).items():
        if isinstance(v, dict) and (k == "props" or k.endswith("_props")):
            out[k] = neo_safe_map(v)
        else:
            out[k] = _safe_leaf(v)
    return out


def _is_neo_driver(obj: Any) -> bool:
    """
    Best-effort check for a Neo4j driver-like object without importing Neo4j.
    """
    return hasattr(obj, "session") or hasattr(obj, "async_session")


def coalesce_driver(driver_like: Any) -> Any | None:
    """
    DEPRECATED: Do not rely on drivers. Use cypher_query(...) instead.

    Behavior (for backward compatibility only):
      - None / 'noop' / 'off' / '' / 'random'  -> None
      - 'auto'                                  -> None (logs deprecation warning)
      - actual driver-like object               -> returned as-is (logs deprecation warning)
      - anything else                           -> None
    """
    # Normalize trivial "no driver" signals
    if driver_like in (None, "noop", "off", "", "random"):
        return None

    # Explicitly remove auto-resolution (no imports, no driver fetch)
    if isinstance(driver_like, str) and driver_like.lower() == "auto":
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        return None

    # Pass through an already-provided driver (strongly discouraged)
    if _is_neo_driver(driver_like):
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        return driver_like

    # Fallback: treat as no driver
    return None


# core/utils/neo/props.py
from __future__ import annotations

import json
from typing import Any

_PRIMS = (str, int, float, bool, type(None))


def neo_safe(value: Any) -> Any:
    # numpy arrays?
    try:
        import numpy as np  # type: ignore

        if isinstance(value, np.ndarray):
            value = value.tolist()
    except Exception:
        pass

    # plain primitives
    if isinstance(value, _PRIMS):
        return value

    # list/tuple
    if isinstance(value, (list, tuple)):
        if all(isinstance(x, _PRIMS) for x in value):
            return list(value)
        # contains non-primitives (e.g., dicts) -> JSON
        return json.dumps(value, ensure_ascii=False)

    # dict or anything else -> JSON
    return json.dumps(value, ensure_ascii=False)


def neo_safe_map(d: dict[str, Any]) -> dict[str, Any]:
    return {k: neo_safe(v) for k, v in d.items()}
