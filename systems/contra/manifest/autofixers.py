from __future__ import annotations

import json


def propose_add_alias_patch(openapi_aliases_path: str, aliases: dict[str, str]) -> dict:
    """
    Propose a JSON patch (not in-place write) to add missing aliases.
    Caller applies through Simula so the diff is reviewable & testable.
    """
    try:
        current = json.loads(open(openapi_aliases_path, encoding="utf-8").read())
    except Exception:
        current = {"aliases": {}}
    proposed = dict(current)
    proposed.setdefault("aliases", {}).update(aliases)
    return {
        "file": openapi_aliases_path,
        "before": current,
        "after": proposed,
        "action": "add_alias",
        "aliases": list(aliases.keys()),
    }


def propose_header_middleware_patch(file_path: str) -> dict:
    """
    Append a tiny helper if missing. Returned as a textual patch (append).
    """
    snippet = """
def attach_eos_headers(headers: dict | None = None, decision_id: str | None = None, budget_ms: int | None = None) -> dict:
    headers = dict(headers or {})
    if decision_id:
        headers.setdefault("x-decision-id", decision_id)
    if budget_ms is not None:
        headers.setdefault("x-budget-ms", str(int(budget_ms)))
    return headers
"""
    return {"file": file_path, "append": snippet, "action": "ensure_header_middleware"}


def propose_swap_http_to_inproc(caller_file: str, callee_symbol: str) -> dict:
    """
    Replace HTTP call with in-proc call via adapter import. Caller will need
    concrete site info; this is a structured suggestion for Simula.
    """
    return {
        "file": caller_file,
        "action": "swap_http_to_inproc",
        "adapter": {"import": callee_symbol, "why": "illegal self-edge"},
    }
