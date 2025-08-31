# systems/atune/planner/costs.py
from __future__ import annotations

from copy import deepcopy

from systems.atune.planner.market import Bid


def scale_bid_costs(bids: list[Bid], price_per_cap: dict[str, float]) -> list[Bid]:
    """
    Returns a NEW list of bids with estimated_cost_ms scaled by Synapse prices.
    - price_per_cap: {"qora:search": 1.15, "maps.geocode": 0.8, ...}
    - Never mutates the original Bid objects.
    - Clamps to [50ms, 30000ms] to avoid pathological values.
    """
    out: list[Bid] = []
    for b in bids:
        cap = getattr(b.action_details, "target_capability", "")
        mult = float(price_per_cap.get(cap, 1.0))
        scaled = int(max(50, min(30000, round(b.estimated_cost_ms * mult))))
        nb = deepcopy(b)
        nb.estimated_cost_ms = scaled
        out.append(nb)
    return out
