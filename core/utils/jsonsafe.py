# core/utils/jsonsafe.py
from __future__ import annotations

import dataclasses
import datetime
import decimal
import json
import uuid
from typing import Any


def _to_jsonable(x: Any) -> Any:
    # --- fast-paths ---
    if x is None or isinstance(x, bool | int | float | str):
        return x

    # dataclasses
    if dataclasses.is_dataclass(x):
        return {k: _to_jsonable(getattr(x, k)) for k in x.__dataclass_fields__.keys()}  # type: ignore[attr-defined]

    # pydantic BaseModel (v1 or v2)
    try:
        from pydantic import BaseModel  # type: ignore

        if isinstance(x, BaseModel):
            # v2: model_dump, v1: dict
            to_dict = getattr(x, "model_dump", None) or getattr(x, "dict", None)
            if callable(to_dict):
                return _to_jsonable(to_dict())
    except Exception:
        pass

    # bytes, UUID, datetime, Decimal
    if isinstance(x, bytes | bytearray):
        return x.decode("utf-8", errors="replace")
    if isinstance(x, uuid.UUID):
        return str(x)
    if isinstance(x, datetime.datetime | datetime.date):
        return x.isoformat()
    if isinstance(x, decimal.Decimal):
        return float(x)

    # containers
    if isinstance(x, dict):
        return {str(_to_jsonable(k)): _to_jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set):
        return [_to_jsonable(i) for i in x]

    # anything else: last-resort string
    return str(x)


def to_jsonable(x: Any) -> Any:
    return _to_jsonable(x)


def dumps_json_safe(x: Any, **kwargs) -> str:
    return json.dumps(_to_jsonable(x), **kwargs)
