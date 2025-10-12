# systems/evo/gates/obviousness.py
from __future__ import annotations

import asyncio

import numpy as np

from core.utils.neo.cypher_query import cypher_query
from systems.evo.schemas import ConflictNode, ObviousnessReport


class ObviousnessGate:
    """
    Async-first gate.
    - Use `await score_async(conflicts)` whenever you’re already in an event loop.
    - `score(conflicts)` is for sync-only contexts (spins a private loop).
    """

    def __init__(self, theta: float = 0.55) -> None:
        self._theta = theta

    async def score_async(self, conflicts: list[ConflictNode]) -> ObviousnessReport:
        if not conflicts:
            return ObviousnessReport(
                conflict_ids=[],
                is_obvious=False,
                score=0.0,
                confidence=1.0,
                model_version="obviousness.local.v1",
                reason="no_conflicts",
            )
        fv = await self._feature_vector(conflicts)
        score, conf = self._combine(fv)
        return ObviousnessReport(
            conflict_ids=[c.conflict_id for c in conflicts],
            is_obvious=score >= self._theta,
            score=score,
            confidence=conf,
            model_version="obviousness.local.v1",
            contributing_features=fv,
            reason="local_gate",
        )

    def score(self, conflicts: list[ConflictNode]) -> ObviousnessReport:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.score_async(conflicts))
        raise RuntimeError(
            "ObviousnessGate.score() called from async context. Use `await score_async(...)`."
        )

    # ---------------- internals ----------------

    async def _feature_vector(self, conflicts: list[ConflictNode]) -> dict[str, float]:
        single = [self._per_conflict_features(c) for c in conflicts]
        hist_fix = await self._historical_fix_rate([c.conflict_id for c in conflicts])
        return {
            "avg_spec_present": float(np.mean([s["spec_present"] for s in single] or [0.0])),
            "avg_spec_gaps": float(np.mean([s["spec_gaps"] for s in single] or [0.0])),
            "avg_reproducer_stable": float(
                np.mean([s["reproducer_stable"] for s in single] or [0.0])
            ),
            "avg_locality": float(np.mean([s["locality"] for s in single] or [0.0])),
            "max_severity": float(np.max([s["severity"] for s in single] or [0.0])),
            "conflict_count": float(len(conflicts)),
            "historical_fix_rate": float(hist_fix),
        }

    def _per_conflict_features(self, c: ConflictNode) -> dict[str, float]:
        # Robust to dict- or model-shaped nested fields
        spec = getattr(c, "spec_coverage", None) or {}
        if hasattr(spec, "has_spec"):
            has_spec = bool(spec.has_spec)
            gaps = list(getattr(spec, "gaps", []) or [])
        else:
            has_spec = bool(spec.get("has_spec", False))
            gaps = list(spec.get("gaps", []) or [])

        reproducer = getattr(c, "reproducer", None) or {}
        if hasattr(reproducer, "stable"):
            repro_stable = bool(reproducer.stable)
        else:
            repro_stable = bool(reproducer.get("stable", False))

        ctx = c.context or {}
        modules = ctx.get("modules", [])
        if not isinstance(modules, list):
            modules = []

        sev_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
        severity = sev_map.get(str(c.severity), 0.5)

        return {
            "spec_present": 1.0 if has_spec else 0.0,
            "spec_gaps": float(len(gaps)),
            "reproducer_stable": 1.0 if repro_stable else 0.0,
            "locality": float(1.0 / max(1, len(modules))),
            "severity": float(severity),
        }

    async def _historical_fix_rate(self, conflict_ids: list[str]) -> float:
        if not conflict_ids:
            return 0.5
        query = """
        UNWIND $cids AS conflict_id
        MATCH (c:Conflict)
        WHERE c.event_id = conflict_id OR c.conflict_id = conflict_id OR c.id = conflict_id
        OPTIONAL MATCH (b)-[r]->(c)
        WHERE type(r) = 'ESCALATES' AND 'EvoBrief' IN labels(b)
        WITH b
        WITH CASE WHEN b IS NULL THEN [] ELSE [apoc.convert.fromJsonMap(b.body)] END AS bodies
        WITH reduce(a=0, d IN bodies |
             a + CASE WHEN d.auction IS NOT NULL AND size(coalesce(d.auction.winners, [])) > 0 THEN 1 ELSE 0 END
        ) AS successes,
        size(bodies) AS attempts
        RETURN attempts, successes
        """
        try:
            rows = await cypher_query(query, params={"cids": conflict_ids})
        except Exception as e:
            msg = str(e).lower()
            if "driver is not initialized" in msg or "init_driver" in msg:
                return 0.5
            raise
        if not rows or not rows[0]:
            return 0.5
        attempts = int(rows[0].get("attempts", 0) or 0)
        successes = int(rows[0].get("successes", 0) or 0)
        return (successes / attempts) if attempts > 0 else 0.5

    def _combine(self, fv: dict[str, float]) -> tuple[float, float]:
        w = {
            "avg_spec_present": +0.30,
            "avg_spec_gaps": -0.15,
            "avg_reproducer_stable": +0.15,
            "avg_locality": +0.15,
            "max_severity": -0.20,
            "conflict_count": -0.05,
            "historical_fix_rate": +0.35,
        }
        score = sum(w[k] * fv.get(k, 0.0) for k in w)
        score = float(np.clip(0.5 + score, 0.0, 1.0))
        conf = float(
            np.clip(
                0.4
                + 0.3 * fv.get("avg_locality", 0.0)
                + 0.2 * fv.get("avg_spec_present", 0.0)
                + 0.2 * fv.get("historical_fix_rate", 0.0)
                - 0.2 * fv.get("max_severity", 0.0),
                0.0,
                1.0,
            ),
        )
        return score, conf
