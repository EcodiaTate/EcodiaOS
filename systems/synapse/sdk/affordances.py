from __future__ import annotations

from typing import Any


def validate_affordance(a: dict[str, Any]) -> None:
    """
    Minimal strict validator to keep affordance payloads predictable.
    """
    if "id" not in a or not isinstance(a["id"], str):
        raise ValueError("Affordance missing 'id' (str).")
    if "kind" not in a or not isinstance(a["kind"], str):
        raise ValueError("Affordance missing 'kind' (str).")
    # Optional fields with common semantics:
    for k in ("cost_est", "risk", "inputs", "acceptance"):
        if k in a and a[k] is None:
            del a[k]


def normalize_affordances(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        validate_affordance(it)
        out.append(it)
    return out
