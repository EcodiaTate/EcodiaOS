# systems/atune/probes/engine.py
from __future__ import annotations

import time
from typing import Any

from systems.atune.processing.canonical import CanonicalEvent


class ProbeEngine:
    """
    Runs cheap, deterministic probes. Each probe returns {ig, risk, details, cost_ms}.
    """

    def __init__(self) -> None:
        pass

    async def run_probes(
        self,
        event: CanonicalEvent,
        priors: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}

        # Web-context proxy (placeholder: compute overlap signal; no network)
        t0 = time.perf_counter()
        ig_web = 0.1 * (1.0 if event.text_blocks else 0.0)
        results["web_context_probe"] = {
            "ig": ig_web,
            "risk": 0.0,
            "details": {"overlap": ig_web},
            "cost_ms": (time.perf_counter() - t0) * 1000.0,
        }

        # KG-context proxy (placeholder: number of tokens as proxy for novelty)
        t1 = time.perf_counter()
        tok_count = sum(len(t.split()) for t in event.text_blocks)
        ig_kg = min(0.5, 0.001 * tok_count)
        results["kg_context_probe"] = {
            "ig": ig_kg,
            "risk": 0.0,
            "details": {"tokens": tok_count},
            "cost_ms": (time.perf_counter() - t1) * 1000.0,
        }

        return results
