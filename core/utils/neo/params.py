# core/utils/neo/params.py
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any


def _coerce(v: Any) -> Any:
    # Pydantic models
    if hasattr(v, "model_dump"):  # pydantic v2
        v = v.model_dump()
    elif hasattr(v, "dict"):  # pydantic v1
        v = v.dict()

    # Enums, datetimes
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, datetime | date):
        return v.isoformat()

    # If string smells like JSON, parse to dict/list (best-effort)
    if isinstance(v, str):
        s = v.strip()
        if s and s[0] in "{[":
            try:
                return json.loads(s)
            except Exception:
                return v  # leave as string if not valid JSON
        return v

    # Recurse into containers
    if isinstance(v, Mapping):
        return {k: _coerce(x) for k, x in v.items()}
    if isinstance(v, list | tuple | set):
        return [_coerce(x) for x in v]
    return v


def neoify_params(params: Mapping[str, Any]) -> dict:
    """Convert a param dict to Neo4j-friendly types (maps/lists), avoiding JSON strings."""
    return {k: _coerce(v) for k, v in params.items()}
