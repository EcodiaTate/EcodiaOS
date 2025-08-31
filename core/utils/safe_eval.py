from __future__ import annotations

from typing import Any

from asteval import Interpreter

_ALLOWED = {"abs": abs, "min": min, "max": max, "sum": sum, "len": len, "round": round}


def safe_eval(expr: str, variables: dict[str, Any] | None = None) -> Any:
    ae = Interpreter(usersyms={**_ALLOWED, **(variables or {})}, no_print=True)
    return ae(expr)
