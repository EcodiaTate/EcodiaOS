# systems/atune/planner/rollback.py
from __future__ import annotations

from typing import Any


def _atom(path: str, op: str, value: Any = None) -> dict[str, Any]:
    return {"path": path, "op": op, **({} if value is None else {"value": value})}


def _safe_noop_contract(note: str) -> dict[str, Any]:
    """
    Safe no-op rollback: never calls Axon. Axon sees capability=None and ignores.
    Still enforced by Atune/Axon journaling.
    """
    return {
        "capability": None,
        "params": {},
        "preconditions": [],
        "postconditions": [],
        "meta": {"kind": "noop", "note": note},
    }


def _map_params_from_result(
    reverse_map: dict[str, str],
    last_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    reverse_map: {"id": "result.resource.id", "parent_id": "result.parent.id"}
    last_result may be None at planning time — we only pre-fill static defaults;
    Axon can re-resolve during rollback execution when the result is present.
    """
    out: dict[str, Any] = {}
    for dest, src_path in (reverse_map or {}).items():
        try:
            if not last_result:
                continue
            # simple dotted-path extractor
            cur: Any = last_result
            for seg in str(src_path).split("."):
                cur = cur[seg]
            out[dest] = cur
        except Exception:
            # leave unset; Axon driver may compute it on rollback execution
            pass
    return out


def synthesize_rollback_contract(
    *,
    capability_spec: dict[str, Any],
    unity_critique: dict[str, Any] | None = None,
    last_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Best-effort, safety-first rollback synthesis.

    capability_spec (optional keys):
      - "rollback_capability": "qora:delete"              # explicit undo cap
      - "reverse_params_map": {"id": "result.id"}         # map from last_result to rollback params
      - "idempotent": true                                # act is idempotent → no rollback call
      - "post_ok_path": "result.status"                   # success path in act result
      - "post_ok_value": "ok"                             # success value
      - "pre_guard": [{"path": "...", "op": "exists"}]    # extra preconditions for rollback
      - "post_guard": [{"path": "...", "op": "equals", "value": "..."}]  # extra postconditions

    unity_critique (optional): full Unity playbook or critique; we include compact pointer.

    If nothing usable is present, returns a safe no-op contract.
    """
    spec = dict(capability_spec or {})
    rollback_cap = spec.get("rollback_capability")
    is_idempotent = bool(spec.get("idempotent", False))

    # If the forward action is idempotent, prefer a no-op rollback.
    if is_idempotent and not rollback_cap:
        return _safe_noop_contract("forward capability declared idempotent; no rollback required")

    if not rollback_cap:
        # No explicit rollback capability — still return no-op to keep invariants.
        return _safe_noop_contract("no rollback_capability provided in capability_spec")

    reverse_map = spec.get("reverse_params_map") or {}
    params = _map_params_from_result(reverse_map, last_result)

    # Guards (pre/post) to keep rollback safe
    preconds: list[dict[str, Any]] = []
    postconds: list[dict[str, Any]] = []

    # Optional pre/post from spec
    if isinstance(spec.get("pre_guard"), list):
        preconds.extend(spec["pre_guard"])
    if isinstance(spec.get("post_guard"), list):
        postconds.extend(spec["post_guard"])

    # Generic post-success check
    ok_path = spec.get("post_ok_path", "result.status")
    ok_val = spec.get("post_ok_value", "ok")
    postconds.append(_atom(ok_path, "equals", ok_val))

    meta = {"kind": "synthesized", "from_spec": True}
    if unity_critique:
        meta["unity_pointer"] = {"has_recommendation": bool(unity_critique.get("recommendation"))}

    return {
        "capability": rollback_cap,
        "params": params,
        "preconditions": preconds,
        "postconditions": postconds,
        "meta": meta,
    }
