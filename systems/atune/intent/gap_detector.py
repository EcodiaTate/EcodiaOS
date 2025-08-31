# systems/atune/intent/gap_detector.py
from __future__ import annotations

from collections import Counter
from typing import Any

from systems.atune.gaps.schema import (
    CapabilityGapEvent,
    ExemplarInput,
    PostconditionFailure,
    RegretStats,
)


def detect_capability_gap(
    decision_id: str,
    chosen_capability: str | None,
    known_capabilities: list[str],
    postcond_errors: list[dict[str, Any]],
    regret_window: list[float],
    trending_hosts: list[str],
    exemplars: list[dict[str, Any]],
    incumbent_driver: str | None = None,
) -> CapabilityGapEvent | None:
    """
    Simple signal fusion to decide if we should fire a gap:
      - Missing capability
      - Chronic postcondition violations
      - Chronic regret@compute
      - Persistent new domains (hosts) not covered by any driver
    """
    missing = chosen_capability and (chosen_capability not in known_capabilities)
    chronic_post = False
    if postcond_errors:
        freq = Counter([(e.get("code") or "unknown") for e in postcond_errors])
        chronic_post = any(c >= 3 for c in freq.values())

    chronic_regret = False
    if regret_window and len(regret_window) >= 5:
        avg = sum(regret_window) / len(regret_window)
        chronic_regret = avg > 0.15  # tune as you like

    new_domains = False
    if trending_hosts:
        # crude: if >60% of trending hosts are not in known capabilities, treat as new domain pressure
        hits = sum(1 for h in trending_hosts if h in (chosen_capability or ""))
        new_domains = (hits / max(1, len(trending_hosts))) < 0.4

    if not (missing or chronic_post or chronic_regret or new_domains):
        return None

    return CapabilityGapEvent(
        decision_id=decision_id,
        missing_capability=chosen_capability if missing else None,
        failing_capability=chosen_capability
        if not missing and (chronic_post or chronic_regret)
        else None,
        exemplars=[
            ExemplarInput(description=e.get("description", ""), payload=e.get("payload", {}))
            for e in exemplars
        ],
        postcondition_violations=[
            PostconditionFailure(code=e.get("code", "unknown"), detail=e.get("detail", ""), count=1)
            for e in postcond_errors
        ],
        regret=RegretStats(
            window=len(regret_window),
            regret_avg=(sum(regret_window) / len(regret_window)) if regret_window else 0.0,
            regret_max=max(regret_window) if regret_window else 0.0,
        ),
        incumbent_driver=incumbent_driver,
        meta={"trending_hosts": trending_hosts},
    )
