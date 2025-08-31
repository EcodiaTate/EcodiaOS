# systems/atune/intent/constraints_merge.py
from __future__ import annotations

from typing import Any

from systems.atune.intent.playbook_schema import Playbook, normalize_playbook

# rollback lives in planner per your layout
from systems.atune.planner.rollback import synthesize_rollback_contract


def _merge_dict(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in (src or {}).items():
        if isinstance(v, dict):
            dst.setdefault(k, {})
            if isinstance(dst[k], dict):
                _merge_dict(dst[k], v)
            else:
                dst[k] = v
        else:
            dst[k] = v


def merge_playbook_into_constraints(
    base_constraints: dict[str, Any] | None,
    playbook: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Returns (merged_constraints, rollback_contract).
    Validates/normalizes the Unity playbook and builds Axon-compatible contract atoms.
    """
    pb: Playbook = normalize_playbook(playbook or {})
    base: dict[str, Any] = dict(base_constraints or {})

    if pb.rate_limits:
        base.setdefault("rate_limits", {})
        _merge_dict(base["rate_limits"], pb.rate_limits.dict(exclude_none=True))
    if pb.redactions:
        base.setdefault("redactions", {})
        _merge_dict(base["redactions"], pb.redactions.dict(exclude_none=True))
    if pb.safety:
        base.setdefault("safety", {})
        _merge_dict(base["safety"], pb.safety.dict(exclude_none=True))

    if pb.preconditions:
        base.setdefault("preconditions", [])
        base["preconditions"].extend([a.dict() for a in pb.preconditions])
    if pb.postconditions:
        base.setdefault("postconditions", [])
        base["postconditions"].extend([a.dict() for a in pb.postconditions])

    rollback_contract = synthesize_rollback_contract(
        capability_spec=pb.capability_spec or {},
        unity_critique=pb.dict(exclude_none=True) if pb.recommendation else None,
    )
    return base, rollback_contract
